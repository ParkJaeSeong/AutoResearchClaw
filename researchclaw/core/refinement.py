"""Durable Stage-13 session preparation over immutable Stage-12 evidence.

This module establishes a bounded refinement session only.  It deliberately
does not assign council work, create candidates, or execute research runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .contracts import (
    REFINEMENT_STAGE_ID,
    REFINEMENT_SUPPORTED_VALIDATION_TYPES,
    get_contract,
)
from .evidence_registration import load_evidence_manifest, registered_evidence_status
from .models import ArtifactRef
from .paths import resolve_project_artifact, validate_relative_path
from .persistence import _fsync_directory
from .project import ResearchProject
from .transactions import project_mutation


SESSION_PATH = "refinement/session.json"
EVIDENCE_PACKET_PATH = "refinement/evidence_packet.json"
_SCHEMA_VERSION = 1
_MAX_SECONDS = 7 * 24 * 60 * 60
_MAX_RECORD_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_ROOT = re.compile(
    r"refinement/candidates/candidate-[0-9]{3}/(code|config|tests|package_metadata)\Z"
)
_PHASE = "awaiting_independent_assessments"
_NEXT_ACTION = "register_refinement_assessment"


@dataclass(frozen=True)
class RefinementEnvelope:
    maximum_runs: int
    maximum_wall_seconds: int
    maximum_candidate_seconds: int
    allowed_input_paths: tuple[str, ...]
    allowed_change_roots: tuple[str, ...]


@dataclass(frozen=True)
class RefinementSessionStatus:
    session_id: str
    phase: str
    evidence_packet_path: str
    evidence_packet_sha256: str
    runs_used: int
    maximum_runs: int
    next_action: str


@dataclass(frozen=True)
class _Baseline:
    manifest: ArtifactRef
    artifacts: tuple[dict[str, object], ...]
    input_paths: tuple[str, ...]


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("refinement_integrity_failure") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_bounded_json(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as error:
        raise ValueError("refinement_integrity_failure") from error
    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode) or initial.st_size > _MAX_RECORD_BYTES:
            raise ValueError("refinement_integrity_failure")
        chunks: list[bytes] = []
        remaining = _MAX_RECORD_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        final = os.fstat(descriptor)
        if (
            len(payload) > _MAX_RECORD_BYTES
            or len(payload) != initial.st_size
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
            raise ValueError("refinement_integrity_failure")
    except OSError as error:
        raise ValueError("refinement_integrity_failure") from error
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("refinement_integrity_failure") from error
    if not isinstance(value, dict):
        raise ValueError("refinement_integrity_failure")
    return value, payload


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if not isinstance(key, str) or key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _positive_int(value: object, name: str, *, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ValueError(f"refinement_envelope_{name}_invalid")
    return value


def _nonempty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"refinement_envelope_{name}_invalid")
    return value


def _parse_envelope(payload: object, *, input_paths: tuple[str, ...]) -> tuple[RefinementEnvelope, str]:
    fields = {
        "schema_version",
        "producer",
        "maximum_runs",
        "maximum_wall_seconds",
        "maximum_candidate_seconds",
        "allowed_input_paths",
        "allowed_change_roots",
    }
    if not isinstance(payload, Mapping) or set(payload) != fields:
        raise ValueError("refinement_envelope_schema_invalid")
    if payload.get("schema_version") != _SCHEMA_VERSION or isinstance(payload.get("schema_version"), bool):
        raise ValueError("refinement_envelope_schema_invalid")
    producer = _nonempty_text(payload["producer"], "producer")
    maximum_runs = _positive_int(payload["maximum_runs"], "maximum_runs", maximum=10)
    maximum_wall_seconds = _positive_int(
        payload["maximum_wall_seconds"], "maximum_wall_seconds", maximum=_MAX_SECONDS
    )
    maximum_candidate_seconds = _positive_int(
        payload["maximum_candidate_seconds"], "maximum_candidate_seconds", maximum=_MAX_SECONDS
    )
    declared_inputs = _paths(payload["allowed_input_paths"], "input")
    if declared_inputs != input_paths:
        raise ValueError("refinement_envelope_inputs_invalid")
    change_roots = _change_roots(payload["allowed_change_roots"])
    return (
        RefinementEnvelope(
            maximum_runs=maximum_runs,
            maximum_wall_seconds=maximum_wall_seconds,
            maximum_candidate_seconds=maximum_candidate_seconds,
            allowed_input_paths=declared_inputs,
            allowed_change_roots=change_roots,
        ),
        producer,
    )


def _paths(value: object, kind: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"refinement_envelope_{kind}s_invalid")
    try:
        paths = tuple(validate_relative_path(path, kind=f"refinement {kind}") for path in value)
    except ValueError as error:
        raise ValueError(f"refinement_envelope_{kind}s_invalid") from error
    if len(paths) != len(set(paths)):
        raise ValueError(f"refinement_envelope_{kind}s_invalid")
    return tuple(sorted(paths))


def _change_roots(value: object) -> tuple[str, ...]:
    paths = _paths(value, "change_root")
    categories: set[str] = set()
    candidate_ids: set[str] = set()
    for path in paths:
        match = _CANDIDATE_ROOT.fullmatch(path)
        if match is None:
            raise ValueError("refinement_envelope_change_roots_invalid")
        candidate_ids.add(path.split("/")[2])
        categories.add(match.group(1))
    if len(candidate_ids) != 1 or categories != {"code", "config", "tests", "package_metadata"}:
        raise ValueError("refinement_envelope_change_roots_invalid")
    return paths


def _artifact(value: object, *, expected_path: str | None = None) -> ArtifactRef:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size"}:
        raise ValueError("refinement_integrity_failure")
    path, digest, size = value["path"], value["sha256"], value["size"]
    if (
        not isinstance(path, str)
        or (expected_path is not None and path != expected_path)
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
    ):
        raise ValueError("refinement_integrity_failure")
    return ArtifactRef(path, digest, size)


def _baseline(project: ResearchProject) -> _Baseline:
    state = project.state
    if state.current_stage != REFINEMENT_STAGE_ID or 12 not in state.completed_stages:
        raise ValueError("refinement_baseline_unavailable")
    try:
        registered = registered_evidence_status(project)
    except ValueError as error:
        raise ValueError("refinement_integrity_failure") from error
    if registered is None:
        raise ValueError("refinement_baseline_unavailable")
    manifest_reference = state.artifacts.get(registered.manifest_path)
    if manifest_reference is None:
        raise ValueError("refinement_integrity_failure")
    try:
        manifest = load_evidence_manifest(project.root, registered.manifest_path)
    except ValueError as error:
        raise ValueError("refinement_integrity_failure") from error
    try:
        manifest_path = resolve_project_artifact(project.root, registered.manifest_path)
        manifest_bytes = manifest_path.read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError("refinement_integrity_failure") from error
    if manifest_reference != ArtifactRef(
        registered.manifest_path, _sha256(manifest_bytes), len(manifest_bytes)
    ):
        raise ValueError("refinement_integrity_failure")
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise ValueError("refinement_integrity_failure")
    artifacts: list[dict[str, object]] = []
    inputs: list[str] = []
    source_paths: set[str] = set()
    for object_entry in objects:
        if not isinstance(object_entry, Mapping) or set(object_entry) != {
            "role", "source_path", "sha256", "size", "object_path"
        }:
            raise ValueError("refinement_integrity_failure")
        source_path = object_entry["source_path"]
        role = object_entry["role"]
        digest = object_entry["sha256"]
        size = object_entry["size"]
        object_path = object_entry["object_path"]
        if (
            not isinstance(source_path, str)
            or not isinstance(role, str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(object_path, str)
            or object_path != f".researchclaw/evidence/objects/{digest}"
            or source_path in source_paths
        ):
            raise ValueError("refinement_integrity_failure")
        source_paths.add(source_path)
        artifacts.append(
            {
                "path": source_path,
                "sha256": digest,
                "size": size,
                "object_path": object_path,
                "role": role,
            }
        )
        if role == "input":
            inputs.append(source_path)
    required_paths = {
        "experiment/design.json",
        "experiment/resources.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    } | set(get_contract(10).required_outputs)
    if not required_paths.issubset(source_paths):
        raise ValueError("refinement_integrity_failure")
    design = next(item for item in artifacts if item["path"] == "experiment/design.json")
    try:
        design_bytes = resolve_project_artifact(project.root, design["object_path"]).read_bytes()
        design_payload = json.loads(design_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("refinement_integrity_failure") from error
    if (
        not isinstance(design_payload, Mapping)
        or design_payload.get("validation_type") not in REFINEMENT_SUPPORTED_VALIDATION_TYPES
    ):
        raise ValueError("refinement_computational_only")
    return _Baseline(
        manifest=manifest_reference,
        artifacts=tuple(sorted(artifacts, key=lambda item: str(item["path"]))),
        input_paths=tuple(sorted(inputs)),
    )


def _envelope_payload(envelope: RefinementEnvelope, producer: str) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "producer": producer,
        "maximum_runs": envelope.maximum_runs,
        "maximum_wall_seconds": envelope.maximum_wall_seconds,
        "maximum_candidate_seconds": envelope.maximum_candidate_seconds,
        "allowed_input_paths": list(envelope.allowed_input_paths),
        "allowed_change_roots": list(envelope.allowed_change_roots),
    }


def _session_id(project_id: str, baseline: _Baseline, envelope: RefinementEnvelope, producer: str) -> str:
    identity = {
        "project_id": project_id,
        "baseline_manifest": {
            "path": baseline.manifest.path,
            "sha256": baseline.manifest.sha256,
            "size": baseline.manifest.size,
        },
        "envelope": _envelope_payload(envelope, producer),
    }
    return _sha256(_canonical_json(identity))[:32]


def _packet_payload(
    *, project_id: str, session_id: str, created_at: str, baseline: _Baseline
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
        "session_id": session_id,
        "producer": "coordinator",
        "created_at": created_at,
        "baseline_manifest": {
            "path": baseline.manifest.path,
            "sha256": baseline.manifest.sha256,
            "size": baseline.manifest.size,
        },
        "artifacts": list(baseline.artifacts),
    }


def _session_payload(
    *,
    project_id: str,
    session_id: str,
    created_at: str,
    producer: str,
    envelope: RefinementEnvelope,
    baseline: _Baseline,
    packet: ArtifactRef,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
        "session_id": session_id,
        "producer": producer,
        "created_at": created_at,
        "envelope": _envelope_payload(envelope, producer),
        "baseline_manifest": {
            "path": baseline.manifest.path,
            "sha256": baseline.manifest.sha256,
            "size": baseline.manifest.size,
        },
        "artifacts": list(baseline.artifacts),
        "evidence_packet": {
            "path": packet.path,
            "sha256": packet.sha256,
            "size": packet.size,
        },
        "phase": _PHASE,
        "runs_used": 0,
        "next_action": _NEXT_ACTION,
    }


def _created_at(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("refinement_integrity_failure")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("refinement_integrity_failure") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("refinement_integrity_failure")
    return value


def _existing_payloads(
    project: ResearchProject,
) -> tuple[dict[str, object] | None, bytes | None, dict[str, object] | None, bytes | None]:
    session_path = resolve_project_artifact(project.root, SESSION_PATH)
    packet_path = resolve_project_artifact(project.root, EVIDENCE_PACKET_PATH)
    session_exists = os.path.lexists(session_path)
    packet_exists = os.path.lexists(packet_path)
    if session_exists and not packet_exists:
        raise ValueError("refinement_integrity_failure")
    if not session_exists:
        if not packet_exists:
            return None, None, None, None
        packet, packet_bytes = _read_bounded_json(packet_path)
        return None, None, packet, packet_bytes
    session, session_bytes = _read_bounded_json(session_path)
    packet, packet_bytes = _read_bounded_json(packet_path)
    return session, session_bytes, packet, packet_bytes


def _status(session: Mapping[str, object]) -> RefinementSessionStatus:
    required = {
        "schema_version", "project_id", "session_id", "producer", "created_at", "envelope",
        "baseline_manifest", "artifacts", "evidence_packet", "phase", "runs_used", "next_action",
    }
    if set(session) != required or session.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("refinement_integrity_failure")
    session_id = session.get("session_id")
    phase = session.get("phase")
    runs_used = session.get("runs_used")
    next_action = session.get("next_action")
    packet = _artifact(session.get("evidence_packet"), expected_path=EVIDENCE_PACKET_PATH)
    envelope = session.get("envelope")
    if (
        not isinstance(session_id, str)
        or not session_id
        or phase != _PHASE
        or not isinstance(runs_used, int)
        or isinstance(runs_used, bool)
        or runs_used != 0
        or next_action != _NEXT_ACTION
        or not isinstance(envelope, Mapping)
        or not isinstance(envelope.get("maximum_runs"), int)
        or isinstance(envelope.get("maximum_runs"), bool)
    ):
        raise ValueError("refinement_integrity_failure")
    return RefinementSessionStatus(
        session_id=session_id,
        phase=phase,
        evidence_packet_path=packet.path,
        evidence_packet_sha256=packet.sha256,
        runs_used=runs_used,
        maximum_runs=envelope["maximum_runs"],
        next_action=next_action,
    )


def _record_state_refs(project: ResearchProject, session: ArtifactRef, packet: ArtifactRef) -> None:
    current = ResearchProject.open(project.root)
    existing_session = current.state.artifacts.get(SESSION_PATH)
    existing_packet = current.state.artifacts.get(EVIDENCE_PACKET_PATH)
    if existing_session not in {None, session} or existing_packet not in {None, packet}:
        raise ValueError("refinement_integrity_failure")
    updated = replace(
        current.state,
        next_action=_NEXT_ACTION,
        artifacts={**current.state.artifacts, SESSION_PATH: session, EVIDENCE_PACKET_PATH: packet},
    )
    if updated != current.state:
        current.persist_state(updated)


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        raise
    except OSError as error:
        raise ValueError("refinement_integrity_failure") from error
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    except OSError as error:
        raise ValueError("refinement_integrity_failure") from error
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _prepare(project: ResearchProject, envelope_payload: object) -> RefinementSessionStatus:
    current = ResearchProject.open(project.root)
    baseline = _baseline(current)
    envelope, producer = _parse_envelope(envelope_payload, input_paths=baseline.input_paths)
    session_id = _session_id(current.state.project_id, baseline, envelope, producer)
    (
        existing_session,
        existing_session_bytes,
        existing_packet,
        existing_packet_bytes,
    ) = _existing_payloads(current)
    if existing_session is None:
        if existing_packet is None:
            created_at = datetime.now(timezone.utc).isoformat()
        else:
            created_at = _created_at(existing_packet.get("created_at"))
    else:
        created_at = _created_at(existing_session.get("created_at"))
    packet_payload = _packet_payload(
        project_id=current.state.project_id,
        session_id=session_id,
        created_at=created_at,
        baseline=baseline,
    )
    packet_bytes = _canonical_json(packet_payload)
    packet_ref = ArtifactRef(EVIDENCE_PACKET_PATH, _sha256(packet_bytes), len(packet_bytes))
    session_payload = _session_payload(
        project_id=current.state.project_id,
        session_id=session_id,
        created_at=created_at,
        producer=producer,
        envelope=envelope,
        baseline=baseline,
        packet=packet_ref,
    )
    session_bytes = _canonical_json(session_payload)
    session_ref = ArtifactRef(SESSION_PATH, _sha256(session_bytes), len(session_bytes))
    if existing_session is not None:
        if existing_session_bytes != session_bytes or existing_packet_bytes != packet_bytes:
            raise ValueError("refinement_integrity_failure")
    elif existing_packet is not None:
        if existing_packet_bytes != packet_bytes:
            raise ValueError("refinement_integrity_failure")
        try:
            _write_exclusive(resolve_project_artifact(current.root, SESSION_PATH), session_bytes)
        except FileExistsError as error:
            raise ValueError("refinement_integrity_failure") from error
    else:
        try:
            _write_exclusive(resolve_project_artifact(current.root, EVIDENCE_PACKET_PATH), packet_bytes)
            _write_exclusive(resolve_project_artifact(current.root, SESSION_PATH), session_bytes)
        except FileExistsError as error:
            raise ValueError("refinement_integrity_failure") from error
    _record_state_refs(current, session_ref, packet_ref)
    return _status(session_payload)


@project_mutation
def prepare_refinement_session(
    project: ResearchProject, envelope_payload: object
) -> RefinementSessionStatus:
    """Create or adopt one exact evidence-bound Stage-13 preparation record."""
    return _prepare(project, envelope_payload)


def load_refinement_session(project: ResearchProject) -> RefinementSessionStatus:
    """Load and fully revalidate the durable preparation records without mutation."""
    current = ResearchProject.open_readonly(project.root)
    baseline = _baseline(current)
    session, session_bytes, packet, packet_bytes = _existing_payloads(current)
    if session is None and packet is None:
        raise ValueError("refinement_baseline_unavailable")
    if session is None or session_bytes is None or packet is None or packet_bytes is None:
        raise ValueError("refinement_integrity_failure")
    envelope_raw = session.get("envelope")
    if not isinstance(envelope_raw, Mapping):
        raise ValueError("refinement_integrity_failure")
    envelope, producer = _parse_envelope(envelope_raw, input_paths=baseline.input_paths)
    session_id = _session_id(current.state.project_id, baseline, envelope, producer)
    created_at = _created_at(session.get("created_at"))
    packet_payload = _packet_payload(
        project_id=current.state.project_id,
        session_id=session_id,
        created_at=created_at,
        baseline=baseline,
    )
    expected_packet = _canonical_json(packet_payload)
    packet_ref = ArtifactRef(EVIDENCE_PACKET_PATH, _sha256(expected_packet), len(expected_packet))
    expected_session = _canonical_json(
        _session_payload(
            project_id=current.state.project_id,
            session_id=session_id,
            created_at=created_at,
            producer=producer,
            envelope=envelope,
            baseline=baseline,
            packet=packet_ref,
        )
    )
    if session_bytes != expected_session or packet_bytes != expected_packet:
        raise ValueError("refinement_integrity_failure")
    session_ref = ArtifactRef(SESSION_PATH, _sha256(expected_session), len(expected_session))
    if (
        current.state.artifacts.get(SESSION_PATH) != session_ref
        or current.state.artifacts.get(EVIDENCE_PACKET_PATH) != packet_ref
    ):
        raise ValueError("refinement_integrity_failure")
    return _status(session)
