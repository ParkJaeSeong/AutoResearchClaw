"""Durable Stage-13 deliberation and candidate registration.

This module prepares bounded sessions, persists council procedure, and registers
closed candidate packages. It does not create candidates, execute them, or
finalize refinement.
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
from .deliberation import (
    Assessment,
    CouncilRole,
    FinalVote,
    Rebuttal,
    decide_council,
    parse_assessment,
    parse_rebuttal,
)
from .evidence_registration import load_evidence_manifest, registered_evidence_status
from .experiment_package_contract import validate_experiment_package_contract_at
from .models import ArtifactRef, ProjectState
from .paths import resolve_project_artifact, validate_relative_path
from .persistence import _fsync_directory
from .project import ResearchProject
from .transactions import project_mutation


SESSION_PATH = "refinement/session.json"
EVIDENCE_PACKET_PATH = "refinement/evidence_packet.json"
_SCHEMA_VERSION = 1
_MAX_SECONDS = 7 * 24 * 60 * 60
_MAX_RECORD_BYTES = 1024 * 1024
_MAX_IDENTITY_FILE_BYTES = 16 * 1024 * 1024
_MAX_IDENTITY_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_IDENTITY_FILES = 256
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_ROOT = re.compile(
    r"refinement/candidates/candidate-[0-9]{3}/(code|config|tests|package_metadata)\Z"
)
_CANDIDATE_NAMESPACE_ROOT = re.compile(
    r"refinement/candidates/(?:\*|\{candidate_id\})/"
    r"(code|config|tests|package_metadata)\Z"
)
_CANDIDATE_FILE_PATH = re.compile(
    r"refinement/candidates/(candidate-[0-9]{3})/"
    r"(code|config|tests|package_metadata)/.+\Z"
)
_ROUND_ID = re.compile(r"round-([0-9]{3})\Z")
_CANDIDATE_ID = re.compile(r"candidate-[0-9]{3}\Z")
_CANDIDATE_RESULT_PATH = re.compile(
    r"refinement/candidates/candidate-[0-9]{3}/results\.json\Z"
)
_CANDIDATE_SELF_TEST_REPORT = re.compile(
    r"refinement/candidates/(candidate-[0-9]{3})/"
    r"package_metadata/self_test_report\.json\Z"
)
_CANDIDATE_SELF_TEST_REGISTRATION = re.compile(
    r"\.researchclaw/refinement-self-tests/([0-9a-f]{32})/"
    r"(candidate-[0-9]{3})\.json\Z"
)
_CANDIDATE_SELF_TEST_PREPARATION = re.compile(
    r"\.researchclaw/refinement-self-tests/([0-9a-f]{32})/"
    r"(candidate-[0-9]{3})\.preparation\.json\Z"
)
_CANDIDATE_SELF_TEST_PREPARATION_INTENT = re.compile(
    r"\.researchclaw/refinement-self-tests/([0-9a-f]{32})/"
    r"(candidate-[0-9]{3})\.preparation\.intent\.json\Z"
)
_PHASE = "awaiting_independent_assessments"
_NEXT_ACTION = "register_refinement_assessment"
_DELIBERATIONS_PATH = "refinement/deliberations"
_CANDIDATE_MANIFEST = re.compile(
    r"refinement/candidates/(candidate-[0-9]{3})/package_metadata/manifest\.json\Z"
)
_DECISION_PATH = re.compile(r"refinement/deliberations/round-[0-9]{3}/decision\.json\Z")
_CANDIDATE_CATEGORIES = frozenset({"code", "config", "tests", "package_metadata"})
_CANDIDATE_MANIFEST_FIELDS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "created_at",
    "decision",
    "change_request",
    "baseline_manifest",
    "baseline_package",
    "unchanged_declarations",
    "package_contract",
    "entry_point",
    "files",
}


@dataclass(frozen=True)
class RefinementAuthority:
    coordinator: str
    implementation: str
    council: tuple[tuple[CouncilRole, str], ...]


@dataclass(frozen=True)
class RefinementEnvelope:
    maximum_runs: int
    maximum_wall_seconds: int
    maximum_candidate_seconds: int
    allowed_input_paths: tuple[str, ...]
    allowed_change_roots: tuple[str, ...]
    authority: RefinementAuthority


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
class CandidateStatus:
    candidate_id: str
    manifest_path: str
    manifest_sha256: str
    decision_sha256: str
    package_contract_sha256: str
    entry_point: str
    files: tuple[ArtifactRef, ...]
    next_action: str


@dataclass(frozen=True)
class _FileSnapshot:
    reference: ArtifactRef
    stat_identity: tuple[int, int, int, int, int, int, int]
    component_identity: tuple[tuple[str, int, int, int], ...]


@dataclass(frozen=True)
class _Baseline:
    manifest: ArtifactRef
    artifacts: tuple[dict[str, object], ...]
    input_paths: tuple[str, ...]


@dataclass(frozen=True)
class _CandidateFile:
    reference: ArtifactRef
    baseline_source_path: str | None
    candidate_only_classification: str | None


@dataclass(frozen=True)
class _RoundBinding:
    round_id: str
    previous_round_id: str | None
    evaluated_artifacts: tuple[ArtifactRef, ...]
    authority: RefinementAuthority


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
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
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
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"refinement_envelope_{name}_invalid")
    return value


def _nonempty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"refinement_envelope_{name}_invalid")
    return value


def _parse_authority(value: object) -> RefinementAuthority:
    if not isinstance(value, Mapping) or set(value) != {
        "coordinator",
        "implementation",
        "council",
    }:
        raise ValueError("refinement_authority_invalid")
    coordinator = value.get("coordinator")
    implementation = value.get("implementation")
    council = value.get("council")
    if (
        not isinstance(coordinator, str)
        or not coordinator.strip()
        or not isinstance(implementation, str)
        or not implementation.strip()
        or not isinstance(council, Mapping)
        or set(council) != {role.value for role in CouncilRole}
    ):
        raise ValueError("refinement_authority_invalid")
    assignments: list[tuple[CouncilRole, str]] = []
    for role in CouncilRole:
        producer = council.get(role.value)
        if not isinstance(producer, str) or not producer.strip():
            raise ValueError("refinement_authority_invalid")
        assignments.append((role, producer))
    producers = [
        coordinator,
        implementation,
        *(producer for _, producer in assignments),
    ]
    if len(producers) != len(set(producers)):
        raise ValueError("refinement_authority_invalid")
    return RefinementAuthority(
        coordinator=coordinator,
        implementation=implementation,
        council=tuple(assignments),
    )


def _authority_payload(authority: RefinementAuthority) -> dict[str, object]:
    return {
        "coordinator": authority.coordinator,
        "implementation": authority.implementation,
        "council": {role.value: producer for role, producer in authority.council},
    }


def _parse_envelope(
    payload: object, *, input_paths: tuple[str, ...]
) -> tuple[RefinementEnvelope, str]:
    fields = {
        "schema_version",
        "producer",
        "maximum_runs",
        "maximum_wall_seconds",
        "maximum_candidate_seconds",
        "allowed_input_paths",
        "allowed_change_roots",
        "authority",
    }
    if not isinstance(payload, Mapping) or set(payload) != fields:
        raise ValueError("refinement_envelope_schema_invalid")
    if payload.get("schema_version") != _SCHEMA_VERSION or isinstance(
        payload.get("schema_version"), bool
    ):
        raise ValueError("refinement_envelope_schema_invalid")
    producer = _nonempty_text(payload["producer"], "producer")
    maximum_runs = _positive_int(payload["maximum_runs"], "maximum_runs", maximum=10)
    maximum_wall_seconds = _positive_int(
        payload["maximum_wall_seconds"], "maximum_wall_seconds", maximum=_MAX_SECONDS
    )
    maximum_candidate_seconds = _positive_int(
        payload["maximum_candidate_seconds"],
        "maximum_candidate_seconds",
        maximum=_MAX_SECONDS,
    )
    declared_inputs = _paths(payload["allowed_input_paths"], "input")
    if declared_inputs != input_paths:
        raise ValueError("refinement_envelope_inputs_invalid")
    change_roots = _change_roots(payload["allowed_change_roots"])
    authority = _parse_authority(payload["authority"])
    return (
        RefinementEnvelope(
            maximum_runs=maximum_runs,
            maximum_wall_seconds=maximum_wall_seconds,
            maximum_candidate_seconds=maximum_candidate_seconds,
            allowed_input_paths=declared_inputs,
            allowed_change_roots=change_roots,
            authority=authority,
        ),
        producer,
    )


def _paths(value: object, kind: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"refinement_envelope_{kind}s_invalid")
    try:
        paths = tuple(
            validate_relative_path(path, kind=f"refinement {kind}") for path in value
        )
    except ValueError as error:
        raise ValueError(f"refinement_envelope_{kind}s_invalid") from error
    if len(paths) != len(set(paths)):
        raise ValueError(f"refinement_envelope_{kind}s_invalid")
    return tuple(sorted(paths))


def _change_roots(value: object) -> tuple[str, ...]:
    paths = _paths(value, "change_root")
    categories: set[str] = set()
    candidate_ids: set[str] = set()
    namespace_tokens: set[str] = set()
    for path in paths:
        match = _CANDIDATE_ROOT.fullmatch(path)
        namespace_match = _CANDIDATE_NAMESPACE_ROOT.fullmatch(path)
        if match is None and namespace_match is None:
            raise ValueError("refinement_envelope_change_roots_invalid")
        token = path.split("/")[2]
        if match is not None:
            candidate_ids.add(token)
            categories.add(match.group(1))
        else:
            namespace_tokens.add(token)
            categories.add(namespace_match.group(1))
    if (
        bool(candidate_ids) == bool(namespace_tokens)
        or len(candidate_ids) > 1
        or len(namespace_tokens) > 1
        or categories
        != {
            "code",
            "config",
            "tests",
            "package_metadata",
        }
    ):
        raise ValueError("refinement_envelope_change_roots_invalid")
    return paths


def _candidate_path_authorized(roots: object, path: str) -> bool:
    if not isinstance(roots, list) or any(not isinstance(root, str) for root in roots):
        return False
    match = _CANDIDATE_FILE_PATH.fullmatch(path)
    if match is None:
        return False
    candidate_id, category = match.groups()
    return any(
        root
        in {
            f"refinement/candidates/{candidate_id}/{category}",
            f"refinement/candidates/*/{category}",
            f"refinement/candidates/{{candidate_id}}/{category}",
        }
        for root in roots
    )


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


def _artifact_payload(reference: ArtifactRef) -> dict[str, object]:
    return {
        "path": reference.path,
        "sha256": reference.sha256,
        "size": reference.size,
    }


def _verify_artifact_identity(project: ResearchProject, reference: ArtifactRef) -> None:
    try:
        path = validate_relative_path(reference.path, kind="refinement evidence")
        destination = resolve_project_artifact(project.root, path)
        descriptor = os.open(
            destination,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except (OSError, ValueError) as error:
        raise ValueError("refinement_round_binding_invalid") from error
    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode) or initial.st_size != reference.size:
            raise ValueError("refinement_round_binding_invalid")
        digest = hashlib.sha256()
        total_size = 0
        remaining = reference.size + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > reference.size:
                raise ValueError("refinement_round_binding_invalid")
            remaining -= len(chunk)
            digest.update(chunk)
        final = os.fstat(descriptor)
        if (
            total_size != reference.size
            or digest.hexdigest() != reference.sha256
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
            raise ValueError("refinement_round_binding_invalid")
    except OSError as error:
        raise ValueError("refinement_round_binding_invalid") from error
    finally:
        os.close(descriptor)


def _evaluated_artifacts(
    project: ResearchProject,
    value: object,
    *,
    session: RefinementSessionStatus,
) -> tuple[ArtifactRef, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("refinement_round_binding_invalid")
    try:
        references = tuple(_artifact(item) for item in value)
    except ValueError as error:
        raise ValueError("refinement_round_binding_invalid") from error
    if len({reference.path for reference in references}) != len(references):
        raise ValueError("refinement_round_binding_invalid")
    _require_identity_budget(references, error_code="refinement_round_binding_invalid")
    for reference in references:
        if (
            reference.path != EVIDENCE_PACKET_PATH
            and _CANDIDATE_RESULT_PATH.fullmatch(reference.path) is None
        ):
            raise ValueError("refinement_round_binding_invalid")
        if project.state.artifacts.get(reference.path) != reference:
            raise ValueError("refinement_round_binding_invalid")
        _verify_artifact_identity(project, reference)
    packet = project.state.artifacts.get(EVIDENCE_PACKET_PATH)
    if (
        packet is None
        or packet.sha256 != session.evidence_packet_sha256
        or packet not in references
    ):
        raise ValueError("refinement_round_binding_invalid")
    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.path != EVIDENCE_PACKET_PATH,
                reference.path,
            ),
        )
    )


def _require_evidence_refs(
    references: tuple[str, ...] | list[object], binding: _RoundBinding
) -> None:
    allowed = {reference.path for reference in binding.evaluated_artifacts}
    if any(
        not isinstance(reference, str) or reference not in allowed
        for reference in references
    ):
        raise ValueError("refinement_evidence_ref_invalid")


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
        _, manifest_bytes = _secure_snapshot(
            project.root,
            registered.manifest_path,
            expected=manifest_reference,
            maximum_bytes=_MAX_RECORD_BYTES,
            read_payload=True,
            error_code="refinement_integrity_failure",
        )
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
            "role",
            "source_path",
            "sha256",
            "size",
            "object_path",
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
    _require_identity_budget(
        (
            manifest_reference,
            *(
                ArtifactRef(
                    str(item["object_path"]),
                    str(item["sha256"]),
                    int(item["size"]),
                )
                for item in artifacts
            ),
        ),
        error_code="refinement_integrity_failure",
    )
    required_paths = {
        "experiment/design.json",
        "experiment/resources.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    } | set(get_contract(10).required_outputs)
    if not required_paths.issubset(source_paths):
        raise ValueError("refinement_integrity_failure")
    design = next(
        item for item in artifacts if item["path"] == "experiment/design.json"
    )
    try:
        design_reference = ArtifactRef(
            str(design["object_path"]), str(design["sha256"]), int(design["size"])
        )
        _, design_bytes = _secure_snapshot(
            project.root,
            design_reference.path,
            expected=design_reference,
            maximum_bytes=design_reference.size,
            read_payload=True,
            error_code="refinement_integrity_failure",
        )
        design_payload = json.loads(design_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("refinement_integrity_failure") from error
    if (
        not isinstance(design_payload, Mapping)
        or design_payload.get("validation_type")
        not in REFINEMENT_SUPPORTED_VALIDATION_TYPES
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
        "authority": _authority_payload(envelope.authority),
    }


def _session_id(
    project_id: str, baseline: _Baseline, envelope: RefinementEnvelope, producer: str
) -> str:
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
    *,
    project_id: str,
    session_id: str,
    created_at: str,
    baseline: _Baseline,
    authority: RefinementAuthority,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
        "session_id": session_id,
        "producer": authority.coordinator,
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
) -> tuple[
    dict[str, object] | None, bytes | None, dict[str, object] | None, bytes | None
]:
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
        "schema_version",
        "project_id",
        "session_id",
        "producer",
        "created_at",
        "envelope",
        "baseline_manifest",
        "artifacts",
        "evidence_packet",
        "phase",
        "runs_used",
        "next_action",
    }
    if set(session) != required or session.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("refinement_integrity_failure")
    session_id = session.get("session_id")
    phase = session.get("phase")
    runs_used = session.get("runs_used")
    next_action = session.get("next_action")
    packet = _artifact(
        session.get("evidence_packet"), expected_path=EVIDENCE_PACKET_PATH
    )
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


def _record_state_refs(
    project: ResearchProject, session: ArtifactRef, packet: ArtifactRef
) -> None:
    current = ResearchProject.open(project.root)
    existing_session = current.state.artifacts.get(SESSION_PATH)
    existing_packet = current.state.artifacts.get(EVIDENCE_PACKET_PATH)
    if existing_session not in {None, session} or existing_packet not in {None, packet}:
        raise ValueError("refinement_integrity_failure")
    updated = replace(
        current.state,
        next_action=_NEXT_ACTION,
        artifacts={
            **current.state.artifacts,
            SESSION_PATH: session,
            EVIDENCE_PACKET_PATH: packet,
        },
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


def _prepare(
    project: ResearchProject, envelope_payload: object
) -> RefinementSessionStatus:
    current = ResearchProject.open(project.root)
    baseline = _baseline(current)
    envelope, producer = _parse_envelope(
        envelope_payload, input_paths=baseline.input_paths
    )
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
        authority=envelope.authority,
    )
    packet_bytes = _canonical_json(packet_payload)
    packet_ref = ArtifactRef(
        EVIDENCE_PACKET_PATH, _sha256(packet_bytes), len(packet_bytes)
    )
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
        if (
            existing_session_bytes != session_bytes
            or existing_packet_bytes != packet_bytes
        ):
            raise ValueError("refinement_integrity_failure")
    elif existing_packet is not None:
        if existing_packet_bytes != packet_bytes:
            raise ValueError("refinement_integrity_failure")
        try:
            _write_exclusive(
                resolve_project_artifact(current.root, SESSION_PATH), session_bytes
            )
        except FileExistsError as error:
            raise ValueError("refinement_integrity_failure") from error
    else:
        try:
            _write_exclusive(
                resolve_project_artifact(current.root, EVIDENCE_PACKET_PATH),
                packet_bytes,
            )
            _write_exclusive(
                resolve_project_artifact(current.root, SESSION_PATH), session_bytes
            )
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


def _load_prepared_refinement_session(
    project: ResearchProject
) -> RefinementSessionStatus:
    """Load and fully revalidate the durable preparation records without mutation."""
    current = ResearchProject.open_readonly(project.root)
    baseline = _baseline(current)
    session, session_bytes, packet, packet_bytes = _existing_payloads(current)
    if session is None and packet is None:
        raise ValueError("refinement_baseline_unavailable")
    if (
        session is None
        or session_bytes is None
        or packet is None
        or packet_bytes is None
    ):
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
        authority=envelope.authority,
    )
    expected_packet = _canonical_json(packet_payload)
    packet_ref = ArtifactRef(
        EVIDENCE_PACKET_PATH, _sha256(expected_packet), len(expected_packet)
    )
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
    session_ref = ArtifactRef(
        SESSION_PATH, _sha256(expected_session), len(expected_session)
    )
    if (
        current.state.artifacts.get(SESSION_PATH) != session_ref
        or current.state.artifacts.get(EVIDENCE_PACKET_PATH) != packet_ref
    ):
        raise ValueError("refinement_integrity_failure")
    return _status(session)


@dataclass(frozen=True)
class _AssessmentAttempt:
    producer: str
    assessment: Assessment | None
    payload: dict[str, object]
    payload_bytes: bytes


def _submission_path(project: ResearchProject, path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        try:
            candidate = resolve_project_artifact(project.root, str(candidate))
        except ValueError as error:
            raise ValueError("refinement_submission_path_invalid") from error
    return candidate


def _submission_base(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    session: RefinementSessionStatus,
    extra_fields: set[str],
    expected_artifacts: tuple[ArtifactRef, ...] | None = None,
) -> tuple[str, tuple[ArtifactRef, ...]]:
    required = {
        "schema_version",
        "project_id",
        "session_id",
        "producer",
        "created_at",
        "artifacts",
    } | extra_fields
    if (
        set(payload) != required
        or payload.get("schema_version") != _SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
    ):
        raise ValueError("refinement_submission_schema_invalid")
    if (
        payload.get("project_id") != project.state.project_id
        or payload.get("session_id") != session.session_id
    ):
        raise ValueError("refinement_submission_binding_invalid")
    producer = payload.get("producer")
    if not isinstance(producer, str) or not producer.strip():
        raise ValueError("refinement_submission_producer_invalid")
    _created_at(payload.get("created_at"))
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("refinement_submission_artifacts_invalid")
    try:
        evaluated = _evaluated_artifacts(project, artifacts, session=session)
    except ValueError as error:
        raise ValueError("refinement_submission_artifacts_invalid") from error
    if expected_artifacts is not None and evaluated != expected_artifacts:
        raise ValueError("refinement_submission_binding_invalid")
    return producer, evaluated


def _prepared_authority(project: ResearchProject) -> RefinementAuthority:
    session, _, _, _ = _existing_payloads(project)
    if session is None or not isinstance(session.get("envelope"), Mapping):
        raise ValueError("refinement_integrity_failure")
    baseline = _baseline(project)
    try:
        envelope, _ = _parse_envelope(
            session["envelope"], input_paths=baseline.input_paths
        )
    except ValueError as error:
        raise ValueError("refinement_integrity_failure") from error
    return envelope.authority


def _round_path(project: ResearchProject, *, create: bool) -> tuple[str, Path] | None:
    root = project.root / _DELIBERATIONS_PATH
    if not root.exists():
        if not create:
            return None
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError("refinement_integrity_failure")
    rounds: list[tuple[int, Path]] = []
    try:
        entries = tuple(root.iterdir())
    except OSError as error:
        raise ValueError("refinement_integrity_failure") from error
    for entry in entries:
        match = _ROUND_ID.fullmatch(entry.name)
        if match is None:
            raise ValueError("refinement_integrity_failure")
        if not entry.is_dir() or entry.is_symlink():
            raise ValueError("refinement_integrity_failure")
        rounds.append((int(match.group(1)), entry))
    if not rounds:
        if not create:
            return None
        return "round-001", root / "round-001"
    rounds.sort()
    if [number for number, _ in rounds] != list(range(1, len(rounds) + 1)):
        raise ValueError("refinement_integrity_failure")
    _, latest = rounds[-1]
    return latest.name, latest


def _round_binding_path(round_id: str) -> str:
    return f"{_DELIBERATIONS_PATH}/{round_id}/round.json"


def _round_binding_payload(
    project: ResearchProject,
    session: RefinementSessionStatus,
    *,
    round_id: str,
    previous_round_id: str | None,
    evaluated_artifacts: tuple[ArtifactRef, ...],
    created_at: str,
) -> dict[str, object]:
    authority = _prepared_authority(project)
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project.state.project_id,
        "session_id": session.session_id,
        "producer": authority.coordinator,
        "created_at": created_at,
        "round_id": round_id,
        "previous_round_id": previous_round_id,
        "evaluated_artifacts": [
            _artifact_payload(reference) for reference in evaluated_artifacts
        ],
        "authority": _authority_payload(authority),
    }


def _load_round_binding(
    project: ResearchProject,
    session: RefinementSessionStatus,
    round_id: str,
) -> _RoundBinding:
    registered = _read_registered_record(project, _round_binding_path(round_id))
    if registered is None:
        raise ValueError("refinement_integrity_failure")
    payload = registered[0]
    required = {
        "schema_version",
        "project_id",
        "session_id",
        "producer",
        "created_at",
        "round_id",
        "previous_round_id",
        "evaluated_artifacts",
        "authority",
    }
    match = _ROUND_ID.fullmatch(round_id)
    number = int(match.group(1)) if match is not None else 0
    previous = None if number == 1 else f"round-{number - 1:03d}"
    authority = _prepared_authority(project)
    if (
        set(payload) != required
        or payload.get("schema_version") != _SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("project_id") != project.state.project_id
        or payload.get("session_id") != session.session_id
        or payload.get("producer") != authority.coordinator
        or payload.get("round_id") != round_id
        or payload.get("previous_round_id") != previous
        or payload.get("authority") != _authority_payload(authority)
    ):
        raise ValueError("refinement_integrity_failure")
    _created_at(payload.get("created_at"))
    try:
        evaluated = _evaluated_artifacts(
            project, payload.get("evaluated_artifacts"), session=session
        )
    except ValueError as error:
        raise ValueError("refinement_integrity_failure") from error
    if payload.get("evaluated_artifacts") != [
        _artifact_payload(reference) for reference in evaluated
    ]:
        raise ValueError("refinement_integrity_failure")
    if previous is not None:
        prior = _load_round_binding(project, session, previous)
        if not _round_is_complete(project, previous) or not set(
            prior.evaluated_artifacts
        ) < set(evaluated):
            raise ValueError("refinement_integrity_failure")
    return _RoundBinding(round_id, previous, evaluated, authority)


def _round_is_complete(project: ResearchProject, round_id: str) -> bool:
    return (
        _read_registered_record(
            project, f"{_DELIBERATIONS_PATH}/{round_id}/decision.json"
        )
        is not None
    )


def _select_assessment_round(
    project: ResearchProject,
    session: RefinementSessionStatus,
    payload: Mapping[str, object],
) -> tuple[_RoundBinding, bytes, bool]:
    try:
        evaluated = _evaluated_artifacts(
            project, payload.get("artifacts"), session=session
        )
    except ValueError as error:
        raise ValueError("refinement_round_binding_invalid") from error
    created_at = _created_at(payload.get("created_at"))
    round_info = _round_path(project, create=True)
    if round_info is None:
        raise ValueError("refinement_integrity_failure")
    round_id, _ = round_info
    binding_path = _round_binding_path(round_id)
    binding_file = resolve_project_artifact(project.root, binding_path)
    binding_registered = binding_path in project.state.artifacts
    if os.path.lexists(binding_file) and not binding_registered:
        number = int(_ROUND_ID.fullmatch(round_id).group(1))
        previous = None if number == 1 else f"round-{number - 1:03d}"
        if previous is not None:
            prior = _load_round_binding(project, session, previous)
            if not _round_is_complete(project, previous) or not set(
                prior.evaluated_artifacts
            ) < set(evaluated):
                raise ValueError("refinement_round_binding_invalid")
        elif evaluated != (project.state.artifacts[EVIDENCE_PACKET_PATH],):
            raise ValueError("refinement_round_binding_invalid")
        orphan = _RoundBinding(
            round_id, previous, evaluated, _prepared_authority(project)
        )
        raw = _canonical_json(
            _round_binding_payload(
                project,
                session,
                round_id=round_id,
                previous_round_id=previous,
                evaluated_artifacts=evaluated,
                created_at=created_at,
            )
        )
        return orphan, raw, True
    if binding_registered:
        latest = _load_round_binding(project, session, round_id)
        if not _round_is_complete(project, round_id):
            if evaluated != latest.evaluated_artifacts:
                raise ValueError("refinement_round_binding_invalid")
            return latest, b"", False
        if evaluated == latest.evaluated_artifacts:
            return latest, b"", False
        if not set(latest.evaluated_artifacts) < set(evaluated):
            raise ValueError("refinement_round_binding_invalid")
        number = int(_ROUND_ID.fullmatch(round_id).group(1)) + 1
        if number > 999:
            raise ValueError("refinement_round_binding_invalid")
        round_id = f"round-{number:03d}"
        if os.path.lexists(project.root / _DELIBERATIONS_PATH / round_id):
            raise ValueError("refinement_integrity_failure")
        previous = latest.round_id
    else:
        expected = project.state.artifacts.get(EVIDENCE_PACKET_PATH)
        if expected is None or evaluated != (expected,):
            raise ValueError("refinement_round_binding_invalid")
        previous = None
    binding = _RoundBinding(
        round_id,
        previous,
        evaluated,
        _prepared_authority(project),
    )
    raw = _canonical_json(
        _round_binding_payload(
            project,
            session,
            round_id=round_id,
            previous_round_id=previous,
            evaluated_artifacts=evaluated,
            created_at=created_at,
        )
    )
    return binding, raw, True


def _record_ref(path: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(path, _sha256(payload), len(payload))


def _read_registered_record(
    project: ResearchProject, relative_path: str
) -> tuple[dict[str, object], bytes] | None:
    path = resolve_project_artifact(project.root, relative_path)
    if not os.path.lexists(path):
        if relative_path in project.state.artifacts:
            raise ValueError("refinement_integrity_failure")
        return None
    payload, raw = _read_bounded_json(path)
    if project.state.artifacts.get(relative_path) != _record_ref(relative_path, raw):
        raise ValueError("refinement_integrity_failure")
    return payload, raw


def _record_state_ref(
    project: ResearchProject, relative_path: str, payload: bytes, *, next_action: str
) -> None:
    current = ResearchProject.open(project.root)
    reference = _record_ref(relative_path, payload)
    existing = current.state.artifacts.get(relative_path)
    if existing not in {None, reference}:
        raise ValueError("refinement_integrity_failure")
    updated = replace(
        current.state,
        next_action=next_action,
        artifacts={**current.state.artifacts, relative_path: reference},
    )
    if updated != current.state:
        current.persist_state(updated)


def _record_next_action(project: ResearchProject, next_action: str) -> None:
    current = ResearchProject.open(project.root)
    if current.state.next_action != next_action:
        current.persist_state(replace(current.state, next_action=next_action))


def _write_registered_record(
    project: ResearchProject,
    relative_path: str,
    payload: bytes,
    *,
    next_action: str,
    conflict: str,
) -> None:
    destination = resolve_project_artifact(project.root, relative_path)
    try:
        _write_exclusive(destination, payload)
    except FileExistsError:
        _, existing = _read_bounded_json(destination)
        if existing != payload:
            raise ValueError(conflict)
    _record_state_ref(project, relative_path, payload, next_action=next_action)


def _adopt_exact_generated_orphan(
    project: ResearchProject,
    relative_path: str,
    expected: bytes,
    *,
    next_action: str,
) -> ResearchProject:
    destination = resolve_project_artifact(project.root, relative_path)
    if not os.path.lexists(destination) or relative_path in project.state.artifacts:
        return project
    _, existing = _read_bounded_json(destination)
    if existing != expected:
        raise ValueError("refinement_integrity_failure")
    _record_state_ref(
        project,
        relative_path,
        expected,
        next_action=next_action,
    )
    return ResearchProject.open(project.root)


def _adopt_exact_assessment_orphan(
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    *,
    role: CouncilRole,
    retry: bool,
    source_payload: Mapping[str, object],
    source_bytes: bytes,
) -> ResearchProject:
    relative_path = (
        f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_retry.json"
        if retry
        else f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_review.json"
    )
    destination = resolve_project_artifact(project.root, relative_path)
    if not os.path.lexists(destination) or relative_path in project.state.artifacts:
        return project
    _, existing_bytes = _read_bounded_json(destination)
    if existing_bytes != source_bytes:
        raise ValueError("refinement_assessment_conflict")
    _assessment_attempt(
        source_payload,
        source_bytes,
        project=project,
        session=session,
        binding=binding,
        role=role,
        retry=retry,
    )
    _record_state_ref(
        project,
        relative_path,
        source_bytes,
        next_action="register_refinement_assessment",
    )
    return ResearchProject.open(project.root)


def _assessment_attempt(
    payload: Mapping[str, object],
    raw: bytes,
    *,
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    role: CouncilRole,
    retry: bool,
) -> _AssessmentAttempt:
    has_assessment = "assessment" in payload
    has_failure = "failure" in payload
    has_retry = "retry" in payload
    if has_assessment == has_failure or has_retry != retry:
        raise ValueError("refinement_assessment_schema_invalid")
    fields = {"role", "assessment"} if has_assessment else {"role", "failure"}
    if retry:
        fields.add("retry")
    producer, _ = _submission_base(
        payload,
        project=project,
        session=session,
        extra_fields=fields,
        expected_artifacts=binding.evaluated_artifacts,
    )
    try:
        submitted_role = CouncilRole(payload["role"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("refinement_assessment_role_invalid") from error
    if submitted_role is not role:
        raise ValueError("refinement_assessment_role_invalid")
    authority = _prepared_authority(project)
    assigned_producers = dict(authority.council)
    if retry:
        retry_value = payload["retry"]
        if (
            not isinstance(retry_value, Mapping)
            or set(retry_value)
            != {"failed_producer", "replacement_producer", "authorized_by"}
            or not isinstance(retry_value.get("failed_producer"), str)
            or not retry_value["failed_producer"].strip()
            or retry_value.get("failed_producer") != assigned_producers[role]
            or retry_value.get("replacement_producer") != producer
            or retry_value.get("authorized_by") != authority.coordinator
            or producer
            in {
                authority.coordinator,
                authority.implementation,
                *assigned_producers.values(),
            }
        ):
            raise ValueError("refinement_retry_authority_invalid")
    elif producer != assigned_producers[role]:
        if producer in assigned_producers.values():
            raise ValueError("refinement_assessment_producer_duplicate")
        raise ValueError("refinement_assessment_producer_invalid")
    if has_failure:
        if not isinstance(payload["failure"], str) or not payload["failure"].strip():
            raise ValueError("refinement_assessment_failure_invalid")
        return _AssessmentAttempt(producer, None, dict(payload), raw)
    try:
        assessment = parse_assessment(
            payload["assessment"],
            expected_binding=session.evidence_packet_sha256,
            expected_role=role,
        )
    except ValueError as error:
        raise ValueError("refinement_assessment_invalid") from error
    _require_evidence_refs(assessment.evidence_refs, binding)
    return _AssessmentAttempt(producer, assessment, dict(payload), raw)


def _assessment_history(
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
) -> dict[CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]]:
    history: dict[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ] = {}
    for role in CouncilRole:
        initial_path = (
            f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_review.json"
        )
        retry_path = f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_retry.json"
        initial_raw = _read_registered_record(project, initial_path)
        retry_raw = _read_registered_record(project, retry_path)
        initial = (
            None
            if initial_raw is None
            else _assessment_attempt(
                initial_raw[0],
                initial_raw[1],
                project=project,
                session=session,
                binding=binding,
                role=role,
                retry=False,
            )
        )
        retry = (
            None
            if retry_raw is None
            else _assessment_attempt(
                retry_raw[0],
                retry_raw[1],
                project=project,
                session=session,
                binding=binding,
                role=role,
                retry=True,
            )
        )
        if retry is not None:
            if initial is None or initial.assessment is not None:
                raise ValueError("refinement_integrity_failure")
            retry_info = retry.payload["retry"]
            if (
                retry_info["failed_producer"] != initial.producer
                or retry.producer == initial.producer
            ):
                raise ValueError("refinement_integrity_failure")
        history[role] = initial, retry
    return history


def _active_assessments(
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
) -> dict[CouncilRole, _AssessmentAttempt]:
    active: dict[CouncilRole, _AssessmentAttempt] = {}
    for role, (initial, retry) in history.items():
        effective = retry if retry is not None else initial
        if effective is not None and effective.assessment is not None:
            if any(
                existing.producer == effective.producer for existing in active.values()
            ):
                raise ValueError("refinement_integrity_failure")
            active[role] = effective
    return active


def _require_distinct_new_assessment_producer(
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
    *,
    role: CouncilRole,
    attempt: _AssessmentAttempt,
) -> None:
    if attempt.assessment is None:
        return
    for other_role, (initial, retry) in history.items():
        if other_role is role:
            continue
        effective = retry if retry is not None else initial
        if (
            effective is not None
            and effective.assessment is not None
            and effective.producer == attempt.producer
        ):
            raise ValueError("refinement_assessment_producer_duplicate")


def _assessment_unresolved(
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
) -> bool:
    for initial, retry in history.values():
        if initial is None or (initial.assessment is None and retry is None):
            return True
    return False


def _failed_retry_count(
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
) -> int:
    return sum(
        retry is not None and retry.assessment is None for _, retry in history.values()
    )


def _vacancy_payload(
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    role: CouncilRole,
    retry: _AssessmentAttempt,
) -> dict[str, object]:
    retry_info = retry.payload["retry"]
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project.state.project_id,
        "session_id": session.session_id,
        "producer": _prepared_authority(project).coordinator,
        "created_at": retry.payload["created_at"],
        "artifacts": [
            _artifact_payload(reference) for reference in binding.evaluated_artifacts
        ],
        "role": role.value,
        "failed_producer": retry_info["failed_producer"],
        "replacement_producer": retry.producer,
        "retry_record_sha256": _sha256(retry.payload_bytes),
    }


def _ensure_vacancy_records(
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
) -> None:
    recorded_vacancies: list[CouncilRole] = []
    failed_retries: list[tuple[CouncilRole, _AssessmentAttempt]] = []
    for role, (_, retry) in history.items():
        relative_path = (
            f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_vacancy.json"
        )
        if retry is not None and retry.assessment is None:
            expected = _canonical_json(
                _vacancy_payload(project, session, binding, role, retry)
            )
            project = _adopt_exact_generated_orphan(
                project,
                relative_path,
                expected,
                next_action="register_refinement_assessment",
            )
        registered = _read_registered_record(project, relative_path)
        if retry is None or retry.assessment is not None:
            if registered is not None:
                raise ValueError("refinement_integrity_failure")
            continue
        failed_retries.append((role, retry))
        if registered is None:
            continue
        if registered[1] != expected:
            raise ValueError("refinement_integrity_failure")
        recorded_vacancies.append(role)
    if len(recorded_vacancies) > 1:
        raise ValueError("refinement_integrity_failure")
    if not recorded_vacancies and failed_retries:
        role, retry = failed_retries[0]
        relative_path = (
            f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_vacancy.json"
        )
        payload = _canonical_json(
            _vacancy_payload(project, session, binding, role, retry)
        )
        _write_registered_record(
            project,
            relative_path,
            payload,
            next_action="register_refinement_assessment",
            conflict="refinement_integrity_failure",
        )


def _vacant_roles(
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    history: Mapping[
        CouncilRole, tuple[_AssessmentAttempt | None, _AssessmentAttempt | None]
    ],
) -> tuple[CouncilRole, ...]:
    vacancies: list[CouncilRole] = []
    for role, (_, retry) in history.items():
        relative_path = (
            f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_vacancy.json"
        )
        registered = _read_registered_record(project, relative_path)
        if retry is None or retry.assessment is not None:
            if registered is not None:
                raise ValueError("refinement_integrity_failure")
            continue
        if registered is None:
            continue
        expected = _canonical_json(
            _vacancy_payload(project, session, binding, role, retry)
        )
        if registered[1] != expected:
            raise ValueError("refinement_integrity_failure")
        vacancies.append(role)
    if len(vacancies) > 1:
        raise ValueError("refinement_integrity_failure")
    return tuple(vacancies)


def _parse_rebuttals_submission(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    assessments: Mapping[CouncilRole, _AssessmentAttempt],
) -> tuple[Rebuttal, ...]:
    producer, _ = _submission_base(
        payload,
        project=project,
        session=session,
        extra_fields={"assessment_hashes", "rebuttals"},
        expected_artifacts=binding.evaluated_artifacts,
    )
    if producer != _prepared_authority(project).coordinator:
        raise ValueError("refinement_coordinator_producer_invalid")
    hashes = payload["assessment_hashes"]
    if not isinstance(hashes, Mapping):
        raise ValueError("refinement_rebuttal_binding_invalid")
    expected_hashes = {
        role.value: _sha256(attempt.payload_bytes)
        for role, attempt in assessments.items()
    }
    if dict(hashes) != expected_hashes:
        raise ValueError("refinement_rebuttal_binding_invalid")
    raw_rebuttals = payload["rebuttals"]
    if not isinstance(raw_rebuttals, list):
        raise ValueError("refinement_rebuttal_schema_invalid")
    parsed: dict[CouncilRole, Rebuttal] = {}
    for item in raw_rebuttals:
        if not isinstance(item, Mapping) or set(item) != {
            "schema_version",
            "role",
            "producer",
            "evidence_packet_sha256",
            "challenges",
            "responses",
            "evidence_refs",
        }:
            raise ValueError("refinement_rebuttal_schema_invalid")
        try:
            role = CouncilRole(item.get("role"))
        except (TypeError, ValueError) as error:
            raise ValueError("refinement_rebuttal_role_invalid") from error
        if role in parsed or role not in assessments:
            raise ValueError("refinement_rebuttal_role_invalid")
        if item.get("producer") != assessments[role].producer:
            raise ValueError("refinement_rebuttal_producer_invalid")
        rebuttal_payload = {
            key: value for key, value in item.items() if key != "producer"
        }
        try:
            parsed[role] = parse_rebuttal(
                rebuttal_payload,
                expected_binding=session.evidence_packet_sha256,
                expected_role=role,
            )
        except ValueError as error:
            raise ValueError("refinement_rebuttal_invalid") from error
        _require_evidence_refs(parsed[role].evidence_refs, binding)
    if set(parsed) != set(assessments):
        raise ValueError("refinement_rebuttal_role_invalid")
    return tuple(parsed[role] for role in CouncilRole if role in parsed)


def _final_votes(
    value: object, *, project: ResearchProject, binding: _RoundBinding
) -> tuple[tuple[FinalVote, str], ...]:
    if not isinstance(value, list):
        raise ValueError("refinement_decision_schema_invalid")
    votes: list[tuple[FinalVote, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("refinement_decision_schema_invalid")
        base_fields = {
            "role",
            "producer",
            "evidence_packet_sha256",
            "decision",
            "rationale",
            "evidence_refs",
        }
        decision = item.get("decision")
        change_seeking = isinstance(decision, str) and decision in {
            "refine",
            "request_discriminating_run",
        }
        expected_fields = base_fields | (
            {"change_request"} if change_seeking else set()
        )
        if set(item) != expected_fields:
            if change_seeking or "change_request" in item:
                raise ValueError("refinement_change_request_invalid")
            raise ValueError("refinement_decision_schema_invalid")
        try:
            role = CouncilRole(item["role"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("refinement_decision_role_invalid") from error
        rationale = item["rationale"]
        evidence_refs = item["evidence_refs"]
        if not isinstance(rationale, list) or not isinstance(evidence_refs, list):
            raise ValueError("refinement_decision_schema_invalid")
        producer = item["producer"]
        if not isinstance(producer, str) or not producer.strip():
            raise ValueError("refinement_final_vote_producer_invalid")
        change_request = (
            _decision_change_request(project, item["change_request"])
            if change_seeking
            else None
        )
        vote = FinalVote(
            role=role,
            evidence_packet_sha256=item["evidence_packet_sha256"],
            decision=item["decision"],
            rationale=tuple(rationale),
            evidence_refs=tuple(evidence_refs),
            change_request=change_request,
        )
        _require_evidence_refs(vote.evidence_refs, binding)
        votes.append((vote, producer))
    return tuple(votes)


def _decision_change_request(
    project: ResearchProject, value: object
) -> tuple[str, ...]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"paths"}
        or not isinstance(value["paths"], list)
    ):
        raise ValueError("refinement_change_request_invalid")
    session_payload, _, _, _ = _existing_payloads(project)
    if session_payload is None or not isinstance(
        session_payload.get("envelope"), Mapping
    ):
        raise ValueError("refinement_integrity_failure")
    roots = session_payload["envelope"].get("allowed_change_roots")
    if not isinstance(roots, list):
        raise ValueError("refinement_integrity_failure")
    try:
        paths = tuple(
            validate_relative_path(path, kind="refinement change")
            for path in value["paths"]
        )
    except ValueError as error:
        raise ValueError("refinement_change_request_invalid") from error
    if (
        not paths
        or len(paths) != len(set(paths))
        or any(not _candidate_path_authorized(roots, path) for path in paths)
        or len(
            {
                match.group(1)
                for path in paths
                if (match := _CANDIDATE_FILE_PATH.fullmatch(path)) is not None
            }
        )
        != 1
    ):
        raise ValueError("refinement_change_request_invalid")
    return paths


def _known_candidate(project: ResearchProject, candidate_id: str) -> bool:
    if _CANDIDATE_ID.fullmatch(candidate_id) is None:
        return False
    prefix = f"refinement/candidates/{candidate_id}/"
    for path, reference in project.state.artifacts.items():
        if path.startswith(prefix) and path.endswith("manifest.json"):
            record = _read_registered_record(project, path)
            if record is not None and _record_ref(path, record[1]) == reference:
                return True
    return False


def _parse_decision_submission(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    session: RefinementSessionStatus,
    binding: _RoundBinding,
    assessments: Mapping[CouncilRole, _AssessmentAttempt],
    rebuttals: tuple[Rebuttal, ...],
    rebuttal_bytes: bytes,
    vacant_roles: tuple[CouncilRole, ...],
):
    action = payload.get("action")
    change_seeking = isinstance(action, str) and action in {
        "refine",
        "request_discriminating_run",
    }
    if change_seeking != ("change_request" in payload):
        raise ValueError("refinement_change_request_invalid")
    top_level_change_request = (
        _decision_change_request(project, payload["change_request"])
        if change_seeking
        else None
    )
    decision_fields = {
        "assessment_hashes",
        "rebuttals_sha256",
        "final_votes",
        "quorum",
        "supporting_roles",
        "dissenting_roles",
        "rationale",
        "evidence_refs",
        "action",
        "candidate_id",
    }
    if change_seeking:
        decision_fields.add("change_request")
    producer, _ = _submission_base(
        payload,
        project=project,
        session=session,
        extra_fields=decision_fields,
        expected_artifacts=binding.evaluated_artifacts,
    )
    if producer != _prepared_authority(project).coordinator:
        raise ValueError("refinement_coordinator_producer_invalid")
    expected_hashes = {
        role.value: _sha256(attempt.payload_bytes)
        for role, attempt in assessments.items()
    }
    if payload["assessment_hashes"] != expected_hashes or payload[
        "rebuttals_sha256"
    ] != _sha256(rebuttal_bytes):
        raise ValueError("refinement_decision_binding_invalid")
    if payload["quorum"] != 2:
        raise ValueError("refinement_decision_quorum_invalid")
    submitted_votes = _final_votes(
        payload["final_votes"], project=project, binding=binding
    )
    for vote, producer in submitted_votes:
        assessment = assessments.get(vote.role)
        if assessment is None or assessment.producer != producer:
            raise ValueError("refinement_final_vote_producer_invalid")
    votes = tuple(vote for vote, _ in submitted_votes)
    try:
        council = decide_council(
            assessments=tuple(attempt.assessment for attempt in assessments.values()),
            rebuttals=rebuttals,
            final_votes=votes,
            vacant_roles=vacant_roles,
        )
    except ValueError as error:
        raise ValueError("refinement_decision_invalid") from error
    if (
        payload["action"] != council.decision
        or payload["supporting_roles"] != list(council.supporting_roles)
        or payload["dissenting_roles"] != list(council.dissenting_roles)
        or not isinstance(payload["rationale"], list)
        or not payload["rationale"]
        or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in payload["rationale"]
        )
        or not isinstance(payload["evidence_refs"], list)
    ):
        raise ValueError("refinement_decision_schema_invalid")
    _require_evidence_refs(payload["evidence_refs"], binding)
    candidate_id = payload["candidate_id"]
    if council.decision == "select_candidate":
        if not isinstance(candidate_id, str) or not _known_candidate(
            project, candidate_id
        ):
            raise ValueError("refinement_candidate_unknown")
    elif candidate_id is not None:
        raise ValueError("refinement_candidate_unknown")
    if council.decision in {"refine", "request_discriminating_run"}:
        if top_level_change_request is None or any(
            vote.change_request != top_level_change_request
            for vote in votes
            if vote.decision == council.decision
        ):
            raise ValueError("refinement_change_request_invalid")
    elif top_level_change_request is not None:
        raise ValueError("refinement_change_request_invalid")
    return council


def _decision_status(
    session: RefinementSessionStatus, decision: str
) -> RefinementSessionStatus:
    if decision in {"refine", "request_discriminating_run"}:
        return replace(
            session,
            phase="awaiting_candidate",
            next_action="register_refinement_candidate",
        )
    return replace(
        session, phase="awaiting_finalization", next_action="finalize_refinement"
    )


def _deliberation_status(project: ResearchProject) -> RefinementSessionStatus:
    session = _load_prepared_refinement_session(project)
    current = ResearchProject.open_readonly(project.root)
    baseline = _baseline(current)
    candidate_statuses = _registered_candidate_statuses(
        current, session=session, baseline=baseline
    )
    from .refinement_execution import (
        _revalidate_registered_intent_semantics,
        _revalidate_registered_preparation_semantics,
        _revalidate_registered_self_test_semantics,
    )

    for candidate in candidate_statuses:
        report_path = (
            f"refinement/candidates/{candidate.candidate_id}/"
            "package_metadata/self_test_report.json"
        )
        registration_path = (
            ".researchclaw/refinement-self-tests/"
            f"{session.session_id}/{candidate.candidate_id}.json"
        )
        preparation_path = (
            ".researchclaw/refinement-self-tests/"
            f"{session.session_id}/{candidate.candidate_id}.preparation.json"
        )
        intent_path = (
            ".researchclaw/refinement-self-tests/"
            f"{session.session_id}/{candidate.candidate_id}.preparation.intent.json"
        )
        if intent_path in current.state.artifacts:
            _revalidate_registered_intent_semantics(current, candidate)
        if preparation_path in current.state.artifacts:
            _revalidate_registered_preparation_semantics(current, candidate)
        if (
            report_path in current.state.artifacts
            and registration_path in current.state.artifacts
        ):
            _revalidate_registered_self_test_semantics(current, candidate)
    round_info = _round_path(current, create=False)
    if round_info is None:
        if candidate_statuses:
            raise ValueError("refinement_candidate_binding_invalid")
        return session
    round_id, _ = round_info
    binding = _load_round_binding(current, session, round_id)
    history = _assessment_history(current, session, binding)
    vacancies = _vacant_roles(current, session, binding, history)
    assessments = _active_assessments(history)
    rebuttal_path = f"{_DELIBERATIONS_PATH}/{round_id}/rebuttals.json"
    rebuttal = _read_registered_record(current, rebuttal_path)
    if rebuttal is None:
        if _failed_retry_count(history) > 1:
            return replace(
                session,
                phase="paused_insufficient_voters",
                next_action="await_approval",
            )
        if _assessment_unresolved(history):
            return session
        if len(assessments) < 2:
            return replace(
                session,
                phase="paused_insufficient_voters",
                next_action="await_approval",
            )
        return replace(
            session,
            phase="awaiting_rebuttals",
            next_action="register_refinement_rebuttals",
        )
    rebuttals = _parse_rebuttals_submission(
        rebuttal[0],
        project=current,
        session=session,
        binding=binding,
        assessments=assessments,
    )
    decision_path = f"{_DELIBERATIONS_PATH}/{round_id}/decision.json"
    decision = _read_registered_record(current, decision_path)
    if decision is None:
        return replace(
            session,
            phase="awaiting_final_votes",
            next_action="register_refinement_final_votes",
        )
    council = _parse_decision_submission(
        decision[0],
        project=current,
        session=session,
        binding=binding,
        assessments=assessments,
        rebuttals=rebuttals,
        rebuttal_bytes=rebuttal[1],
        vacant_roles=vacancies,
    )
    decision_status = _decision_status(session, council.decision)
    if council.decision in {"refine", "request_discriminating_run"}:
        decision_sha256 = _sha256(decision[1])
        matching_candidates = tuple(
            candidate
            for candidate in candidate_statuses
            if candidate.decision_sha256 == decision_sha256
        )
        if len(matching_candidates) > 1:
            raise ValueError("refinement_candidate_binding_invalid")
        if matching_candidates:
            if current.state.next_action not in {
                "prepare_refinement_self_test",
                "prepare_refinement_run",
            }:
                raise ValueError("refinement_candidate_binding_invalid")
            return replace(
                decision_status,
                phase=(
                    "awaiting_self_test"
                    if current.state.next_action == "prepare_refinement_self_test"
                    else "awaiting_candidate_run"
                ),
                next_action=current.state.next_action,
            )
        if current.state.next_action == "prepare_refinement_self_test":
            raise ValueError("refinement_candidate_binding_invalid")
    return decision_status


@project_mutation
def register_refinement_assessment(
    project: ResearchProject, path: str | Path
) -> RefinementSessionStatus:
    """Durably register one role's independent initial assessment or one retry."""
    current = ResearchProject.open(project.root)
    session = _load_prepared_refinement_session(current)
    source_payload, source_bytes = _read_bounded_json(_submission_path(current, path))
    role_value = source_payload.get("role")
    try:
        role = CouncilRole(role_value)
    except (TypeError, ValueError) as error:
        raise ValueError("refinement_assessment_role_invalid") from error
    wants_retry = "retry" in source_payload
    binding, binding_bytes, create_binding = _select_assessment_round(
        current, session, source_payload
    )
    attempt: _AssessmentAttempt | None = None
    if create_binding:
        attempt = _assessment_attempt(
            source_payload,
            source_bytes,
            project=current,
            session=session,
            binding=binding,
            role=role,
            retry=wants_retry,
        )
        if wants_retry:
            raise ValueError("refinement_retry_order_invalid")
        _write_registered_record(
            current,
            _round_binding_path(binding.round_id),
            binding_bytes,
            next_action="register_refinement_assessment",
            conflict="refinement_round_binding_invalid",
        )
        current = ResearchProject.open(current.root)
    current = _adopt_exact_assessment_orphan(
        current,
        session,
        binding,
        role=role,
        retry=wants_retry,
        source_payload=source_payload,
        source_bytes=source_bytes,
    )
    history = _assessment_history(current, session, binding)
    initial, retry = history[role]
    if initial is None:
        if wants_retry:
            raise ValueError("refinement_retry_order_invalid")
        if attempt is None:
            attempt = _assessment_attempt(
                source_payload,
                source_bytes,
                project=current,
                session=session,
                binding=binding,
                role=role,
                retry=False,
            )
        _require_distinct_new_assessment_producer(history, role=role, attempt=attempt)
        target = f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_review.json"
    elif initial.assessment is not None:
        target = f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_review.json"
        if source_bytes != initial.payload_bytes:
            raise ValueError("refinement_assessment_conflict")
    elif retry is None:
        if not wants_retry:
            if source_bytes != initial.payload_bytes:
                raise ValueError("refinement_assessment_conflict")
            return _deliberation_status(current)
        if attempt is None:
            attempt = _assessment_attempt(
                source_payload,
                source_bytes,
                project=current,
                session=session,
                binding=binding,
                role=role,
                retry=True,
            )
        retry_info = attempt.payload["retry"]
        if (
            retry_info["failed_producer"] != initial.producer
            or attempt.producer == initial.producer
        ):
            raise ValueError("refinement_retry_authority_invalid")
        _require_distinct_new_assessment_producer(history, role=role, attempt=attempt)
        target = f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_retry.json"
    else:
        target = f"{_DELIBERATIONS_PATH}/{binding.round_id}/{role.value}_retry.json"
        if source_bytes != retry.payload_bytes:
            raise ValueError("refinement_assessment_conflict")
    _write_registered_record(
        current,
        target,
        source_bytes,
        next_action="register_refinement_assessment",
        conflict="refinement_assessment_conflict",
    )
    persisted = ResearchProject.open(current.root)
    history = _assessment_history(persisted, session, binding)
    _ensure_vacancy_records(persisted, session, binding, history)
    status = _deliberation_status(ResearchProject.open(current.root))
    _record_next_action(current, status.next_action)
    return status


@project_mutation
def register_refinement_rebuttals(
    project: ResearchProject, path: str | Path
) -> RefinementSessionStatus:
    """Disclose and persist rebuttals only after all initial roles are resolved."""
    current = ResearchProject.open(project.root)
    session = _load_prepared_refinement_session(current)
    round_info = _round_path(current, create=False)
    if round_info is None:
        raise ValueError("refinement_disclosure_order_invalid")
    round_id, _ = round_info
    binding = _load_round_binding(current, session, round_id)
    history = _assessment_history(current, session, binding)
    assessments = _active_assessments(history)
    if _assessment_unresolved(history) or len(assessments) < 2:
        raise ValueError("refinement_disclosure_order_invalid")
    source_payload, source_bytes = _read_bounded_json(_submission_path(current, path))
    _parse_rebuttals_submission(
        source_payload,
        project=current,
        session=session,
        binding=binding,
        assessments=assessments,
    )
    _write_registered_record(
        current,
        f"{_DELIBERATIONS_PATH}/{round_id}/rebuttals.json",
        source_bytes,
        next_action="register_refinement_final_votes",
        conflict="refinement_rebuttal_conflict",
    )
    return _deliberation_status(ResearchProject.open(current.root))


def load_refinement_session(project: ResearchProject) -> RefinementSessionStatus:
    """Load the session and reconstruct its verified durable deliberation phase."""
    return _deliberation_status(project)


@project_mutation
def register_refinement_decision(
    project: ResearchProject, path: str | Path
) -> RefinementSessionStatus:
    """Persist final votes atomically with their quorum-backed council decision."""
    current = ResearchProject.open(project.root)
    session = _load_prepared_refinement_session(current)
    round_info = _round_path(current, create=False)
    if round_info is None:
        raise ValueError("refinement_disclosure_order_invalid")
    round_id, _ = round_info
    binding = _load_round_binding(current, session, round_id)
    history = _assessment_history(current, session, binding)
    if _assessment_unresolved(history):
        raise ValueError("refinement_disclosure_order_invalid")
    vacancies = _vacant_roles(current, session, binding, history)
    assessments = _active_assessments(history)
    rebuttal_path = f"{_DELIBERATIONS_PATH}/{round_id}/rebuttals.json"
    rebuttal = _read_registered_record(current, rebuttal_path)
    if rebuttal is None:
        raise ValueError("refinement_disclosure_order_invalid")
    rebuttals = _parse_rebuttals_submission(
        rebuttal[0],
        project=current,
        session=session,
        binding=binding,
        assessments=assessments,
    )
    source_payload, source_bytes = _read_bounded_json(_submission_path(current, path))
    council = _parse_decision_submission(
        source_payload,
        project=current,
        session=session,
        binding=binding,
        assessments=assessments,
        rebuttals=rebuttals,
        rebuttal_bytes=rebuttal[1],
        vacant_roles=vacancies,
    )
    next_status = _decision_status(session, council.decision)
    _write_registered_record(
        current,
        f"{_DELIBERATIONS_PATH}/{round_id}/decision.json",
        source_bytes,
        next_action=next_status.next_action,
        conflict="refinement_decision_conflict",
    )
    return _deliberation_status(ResearchProject.open(current.root))


def _candidate_manifest_relative_path(
    project: ResearchProject, manifest_path: str | Path
) -> tuple[str, str, Path]:
    candidate = Path(manifest_path)
    root = project.root.resolve(strict=True)
    if candidate.is_absolute():
        relative = None
        for boundary in range(1, len(candidate.parts) + 1):
            try:
                prefix = Path(*candidate.parts[:boundary]).resolve(strict=True)
            except (OSError, RuntimeError):
                break
            if prefix == root:
                suffix = candidate.parts[boundary:]
                if suffix:
                    relative = Path(*suffix).as_posix()
                break
        if relative is None:
            raise ValueError("refinement_candidate_path_invalid")
    else:
        relative = candidate.as_posix()
    match = _CANDIDATE_MANIFEST.fullmatch(relative)
    if match is None:
        raise ValueError("refinement_candidate_path_invalid")
    try:
        resolved = resolve_project_artifact(project.root, relative)
    except ValueError as error:
        raise ValueError("refinement_candidate_path_invalid") from error
    return relative, match.group(1), resolved


def _secure_snapshot(
    root: Path,
    relative_path: str,
    *,
    expected: ArtifactRef | None = None,
    maximum_bytes: int | None = None,
    read_payload: bool = False,
    error_code: str,
    size_error_code: str | None = None,
) -> tuple[_FileSnapshot, bytes]:
    size_error_code = size_error_code or error_code
    if expected is not None:
        if expected.size > _MAX_IDENTITY_FILE_BYTES:
            raise ValueError(size_error_code)
        maximum_bytes = min(
            expected.size,
            maximum_bytes if maximum_bytes is not None else _MAX_IDENTITY_FILE_BYTES,
        )
    elif maximum_bytes is None or maximum_bytes > _MAX_IDENTITY_FILE_BYTES:
        maximum_bytes = _MAX_IDENTITY_FILE_BYTES
    try:
        relative_path = validate_relative_path(
            relative_path, kind="refinement candidate"
        )
        path = resolve_project_artifact(root, relative_path)
        root_path = root.resolve(strict=True)
        component_identity: list[tuple[str, int, int, int]] = []
        cursor = root_path
        for part in Path(relative_path).parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(error_code)
            component_identity.append(
                (part, metadata.st_dev, metadata.st_ino, metadata.st_ctime_ns)
            )
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except (OSError, ValueError) as error:
        raise ValueError(error_code) from error
    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
            raise ValueError(error_code)
        if expected is not None and initial.st_size != expected.size:
            raise ValueError(error_code)
        if initial.st_size > maximum_bytes:
            raise ValueError(size_error_code)
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        total_size = 0
        while True:
            read_size = 64 * 1024
            read_size = min(read_size, maximum_bytes - total_size + 1)
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > maximum_bytes:
                raise ValueError(size_error_code)
            if read_payload:
                chunks.append(chunk)
            digest.update(chunk)
        payload = b"".join(chunks) if read_payload else b""
        final = os.fstat(descriptor)
        identity = (
            initial.st_dev,
            initial.st_ino,
            initial.st_mode,
            initial.st_nlink,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        )
        if identity != (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            raise ValueError(error_code)
        reference = ArtifactRef(relative_path, digest.hexdigest(), initial.st_size)
        if expected is not None and reference != expected:
            raise ValueError(error_code)
        return (
            _FileSnapshot(reference, identity, tuple(component_identity)),
            payload,
        )
    except OSError as error:
        raise ValueError(error_code) from error
    finally:
        os.close(descriptor)


def _require_identity_budget(
    references: tuple[ArtifactRef, ...], *, error_code: str
) -> None:
    if (
        len(references) > _MAX_IDENTITY_FILES
        or any(reference.size > _MAX_IDENTITY_FILE_BYTES for reference in references)
        or sum(reference.size for reference in references) > _MAX_IDENTITY_TOTAL_BYTES
    ):
        raise ValueError(error_code)


def _baseline_registration_snapshot(
    project: ResearchProject, baseline: _Baseline
) -> tuple[_FileSnapshot, ...]:
    paths = [baseline.manifest.path]
    paths.extend(str(item["object_path"]) for item in baseline.artifacts)
    expected_references: list[ArtifactRef] = []
    for path in sorted(set(paths)):
        expected = (
            baseline.manifest
            if path == baseline.manifest.path
            else next(
                ArtifactRef(
                    str(item["object_path"]),
                    str(item["sha256"]),
                    int(item["size"]),
                )
                for item in baseline.artifacts
                if item["object_path"] == path
            )
        )
        expected_references.append(expected)
    _require_identity_budget(
        tuple(expected_references), error_code="refinement_candidate_baseline_changed"
    )
    snapshots: list[_FileSnapshot] = []
    for expected in expected_references:
        snapshot, _ = _secure_snapshot(
            project.root,
            expected.path,
            expected=expected,
            maximum_bytes=expected.size,
            error_code="refinement_candidate_baseline_changed",
        )
        snapshots.append(snapshot)
    return tuple(snapshots)


def _same_published_baseline_snapshot(
    before: tuple[_FileSnapshot, ...], after: tuple[_FileSnapshot, ...]
) -> bool:
    """Ignore only the shared .researchclaw directory ctime changed by state write."""

    def stable_components(snapshot: _FileSnapshot):
        return tuple(
            (
                name,
                device,
                inode,
                None if index == 0 and name == ".researchclaw" else ctime,
            )
            for index, (name, device, inode, ctime) in enumerate(
                snapshot.component_identity
            )
        )

    return len(before) == len(after) and all(
        left.reference == right.reference
        and left.stat_identity == right.stat_identity
        and stable_components(left) == stable_components(right)
        for left, right in zip(before, after, strict=True)
    )


def _baseline_artifact_bytes(
    project: ResearchProject, baseline: _Baseline, source_path: str
) -> bytes:
    try:
        item = next(
            entry for entry in baseline.artifacts if entry["path"] == source_path
        )
    except StopIteration as error:
        raise ValueError("refinement_candidate_binding_invalid") from error
    expected = ArtifactRef(
        str(item["object_path"]), str(item["sha256"]), int(item["size"])
    )
    _, payload = _secure_snapshot(
        project.root,
        expected.path,
        expected=expected,
        maximum_bytes=expected.size,
        read_payload=True,
        error_code="refinement_candidate_baseline_changed",
    )
    return payload


def _config_argument(argv: object) -> str:
    if (
        not isinstance(argv, (list, tuple))
        or any(not isinstance(item, str) for item in argv)
        or argv.count("--config") != 1
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    position = argv.index("--config")
    if position + 1 >= len(argv) or not argv[position + 1]:
        raise ValueError("refinement_candidate_binding_invalid")
    return argv[position + 1]


def _canonical_candidate_baseline_sources(
    *,
    baseline: _Baseline,
    baseline_contract: Mapping[str, object],
    baseline_manifest: Mapping[str, object],
    candidate_contract: Mapping[str, object],
    candidate_entry_point: str,
    candidate_self_test_argv: tuple[str, ...],
    candidate_execution_argv: tuple[str, ...],
    candidate_contract_path: str,
    prefix: str,
) -> tuple[dict[str, str], frozenset[str]]:
    """Derive semantic destination provenance without trusting candidate claims."""
    baseline_self_test = baseline_contract.get("self_test")
    candidate_self_test = candidate_contract.get("self_test")
    if not isinstance(baseline_self_test, Mapping) or not isinstance(
        candidate_self_test, Mapping
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    baseline_entry_point = baseline_contract.get("entry_point")
    baseline_config = baseline_contract.get("config_path")
    baseline_fixture = baseline_self_test.get("fixture_path")
    candidate_config = candidate_contract.get("config_path")
    candidate_fixture = candidate_self_test.get("fixture_path")
    semantic_values = (
        baseline_entry_point,
        baseline_config,
        baseline_fixture,
        candidate_config,
        candidate_fixture,
    )
    if any(not isinstance(value, str) or not value for value in semantic_values):
        raise ValueError("refinement_candidate_binding_invalid")
    baseline_self_test_config = _config_argument(baseline_self_test.get("argv_suffix"))
    candidate_self_test_config = _config_argument(candidate_self_test_argv)
    if _config_argument(candidate_execution_argv) != candidate_config:
        raise ValueError("refinement_candidate_binding_invalid")

    baseline_by_path = {str(item["path"]): item for item in baseline.artifacts}
    manifest_files = baseline_manifest.get("files")
    if not isinstance(manifest_files, list):
        raise ValueError("refinement_candidate_binding_invalid")
    manifest_identities: dict[str, str] = {}
    for raw in manifest_files:
        if not isinstance(raw, Mapping):
            raise ValueError("refinement_candidate_binding_invalid")
        path, digest = raw.get("path"), raw.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or path in manifest_identities
        ):
            raise ValueError("refinement_candidate_binding_invalid")
        manifest_identities[path] = digest
    for source_path in (
        baseline_entry_point,
        baseline_config,
        baseline_self_test_config,
    ):
        baseline_item = baseline_by_path.get(source_path)
        if (
            baseline_item is None
            or manifest_identities.get(source_path) != baseline_item["sha256"]
        ):
            raise ValueError("refinement_candidate_binding_invalid")

    role_pairs = (
        (candidate_entry_point, baseline_entry_point),
        (candidate_config, baseline_config),
        (candidate_self_test_config, baseline_self_test_config),
        (candidate_fixture, baseline_fixture),
        (candidate_contract_path, "experiment/package_contract.json"),
        ("package_metadata/package_manifest.json", "experiment/package_manifest.json"),
    )
    semantic_destinations = frozenset(f"{prefix}{path}" for path, _ in role_pairs)
    canonical_sources = {
        f"{prefix}{destination}": source
        for destination, source in role_pairs
        if source in baseline_by_path
    }
    return canonical_sources, semantic_destinations


def _candidate_file_references(
    project: ResearchProject,
    *,
    candidate_id: str,
    manifest_path: str,
    value: object,
    baseline: _Baseline,
) -> tuple[tuple[_CandidateFile, ...], tuple[_FileSnapshot, ...]]:
    if not isinstance(value, list) or not value:
        raise ValueError("refinement_candidate_schema_invalid")
    prefix = f"refinement/candidates/{candidate_id}/"
    candidate_files: list[_CandidateFile] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {
            "path",
            "sha256",
            "size",
            "provenance",
        }:
            raise ValueError("refinement_candidate_schema_invalid")
        try:
            reference = _artifact({key: raw[key] for key in ("path", "sha256", "size")})
        except ValueError as error:
            raise ValueError("refinement_candidate_schema_invalid") from error
        provenance = raw["provenance"]
        baseline_source_path: str | None = None
        candidate_only_classification: str | None = None
        if (
            isinstance(provenance, Mapping)
            and set(provenance) == {"kind", "source_path"}
            and provenance.get("kind") == "stage12_evidence"
            and isinstance(provenance.get("source_path"), str)
        ):
            baseline_source_path = provenance["source_path"]
            if not any(
                item["path"] == baseline_source_path for item in baseline.artifacts
            ):
                raise ValueError("refinement_candidate_provenance_invalid")
        elif (
            isinstance(provenance, Mapping)
            and set(provenance) == {"kind", "classification"}
            and provenance.get("kind") == "candidate_only"
            and provenance.get("classification") == "self_test_fixture"
        ):
            if any(
                item["path"] == "experiment/self_test_fixture.json"
                for item in baseline.artifacts
            ):
                raise ValueError("refinement_candidate_provenance_invalid")
            candidate_only_classification = "self_test_fixture"
        else:
            raise ValueError("refinement_candidate_provenance_invalid")
        try:
            normalized = validate_relative_path(
                reference.path, kind="refinement candidate file"
            )
        except ValueError as error:
            raise ValueError("refinement_candidate_path_invalid") from error
        if normalized != reference.path or not reference.path.startswith(prefix):
            raise ValueError("refinement_candidate_path_invalid")
        local = reference.path.removeprefix(prefix)
        parts = Path(local).parts
        if (
            len(parts) < 2
            or parts[0] not in _CANDIDATE_CATEGORIES
            or reference.path == manifest_path
        ):
            raise ValueError("refinement_candidate_path_invalid")
        candidate_files.append(
            _CandidateFile(
                reference,
                baseline_source_path,
                candidate_only_classification,
            )
        )
    references = tuple(item.reference for item in candidate_files)
    if len({reference.path for reference in references}) != len(references):
        raise ValueError("refinement_candidate_schema_invalid")
    baseline_sources = tuple(
        item.baseline_source_path
        for item in candidate_files
        if item.baseline_source_path is not None
    )
    if len(baseline_sources) != len(set(baseline_sources)):
        raise ValueError("refinement_candidate_provenance_invalid")
    _require_identity_budget(references, error_code="refinement_candidate_size_invalid")
    snapshots = [
        _secure_snapshot(
            project.root,
            reference.path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_candidate_identity_changed",
            size_error_code="refinement_candidate_size_invalid",
        )[0]
        for reference in references
    ]
    return (
        tuple(sorted(candidate_files, key=lambda item: item.reference.path)),
        tuple(sorted(snapshots, key=lambda snapshot: snapshot.reference.path)),
    )


def _require_closed_candidate_tree(
    root: Path,
    *,
    manifest_path: str,
    references: tuple[ArtifactRef, ...],
    additional_paths: tuple[str, ...] = (),
) -> None:
    expected = (
        {reference.path for reference in references}
        | {manifest_path}
        | set(additional_paths)
    )
    found: set[str] = set()
    try:
        for directory, directory_names, file_names in os.walk(
            root, topdown=True, followlinks=False
        ):
            directory_path = Path(directory)
            for name in directory_names:
                child = directory_path / name
                if child.is_symlink():
                    raise ValueError("refinement_candidate_identity_changed")
            for name in file_names:
                child = directory_path / name
                metadata = child.stat(follow_symlinks=False)
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                ):
                    raise ValueError("refinement_candidate_identity_changed")
                found.add(child.relative_to(root.parent.parent.parent).as_posix())
    except OSError as error:
        raise ValueError("refinement_candidate_path_invalid") from error
    if found != expected:
        raise ValueError("refinement_candidate_manifest_open")


def _parse_candidate_manifest(
    project: ResearchProject,
    *,
    manifest_path: str,
    candidate_id: str,
    manifest: Mapping[str, object],
    session: RefinementSessionStatus,
    baseline: _Baseline,
) -> tuple[
    tuple[ArtifactRef, ...],
    tuple[_FileSnapshot, ...],
    ArtifactRef,
    str,
    str,
]:
    if (
        set(manifest) != _CANDIDATE_MANIFEST_FIELDS
        or manifest.get("schema_version") != _SCHEMA_VERSION
        or isinstance(manifest.get("schema_version"), bool)
        or manifest.get("project_id") != project.state.project_id
        or manifest.get("session_id") != session.session_id
        or manifest.get("candidate_id") != candidate_id
    ):
        raise ValueError("refinement_candidate_schema_invalid")
    _created_at(manifest.get("created_at"))
    authority = _prepared_authority(project)
    producer = manifest.get("producer")
    if producer != authority.implementation:
        raise ValueError("refinement_candidate_producer_invalid")

    declared_decision_value = manifest.get("decision")
    if not isinstance(declared_decision_value, Mapping):
        raise ValueError("refinement_candidate_binding_invalid")
    decision_path_value = declared_decision_value.get("path")
    if (
        not isinstance(decision_path_value, str)
        or _DECISION_PATH.fullmatch(decision_path_value) is None
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    decision_path = decision_path_value
    decision_record = _read_registered_record(project, decision_path)
    if decision_record is None:
        raise ValueError("refinement_candidate_binding_invalid")
    decision_ref = _record_ref(decision_path, decision_record[1])
    try:
        declared_decision = _artifact(manifest.get("decision"))
    except ValueError as error:
        raise ValueError("refinement_candidate_binding_invalid") from error
    if declared_decision != decision_ref:
        raise ValueError("refinement_candidate_binding_invalid")
    vote_producers = {
        vote.get("producer")
        for vote in decision_record[0].get("final_votes", [])
        if isinstance(vote, Mapping)
    }
    if producer in vote_producers:
        raise ValueError("refinement_candidate_producer_invalid")
    change_request = decision_record[0].get("change_request")
    if manifest.get("change_request") != change_request:
        raise ValueError("refinement_candidate_binding_invalid")

    try:
        declared_baseline = _artifact(manifest.get("baseline_manifest"))
    except ValueError as error:
        raise ValueError("refinement_candidate_binding_invalid") from error
    if declared_baseline != baseline.manifest:
        raise ValueError("refinement_candidate_binding_invalid")

    candidate_files, snapshots = _candidate_file_references(
        project,
        candidate_id=candidate_id,
        manifest_path=manifest_path,
        value=manifest.get("files"),
        baseline=baseline,
    )
    references = tuple(item.reference for item in candidate_files)
    reference_paths = {reference.path for reference in references}
    if not isinstance(change_request, Mapping) or set(change_request) != {"paths"}:
        raise ValueError("refinement_candidate_binding_invalid")
    requested_paths = change_request.get("paths")
    if (
        not isinstance(requested_paths, list)
        or not requested_paths
        or any(path not in reference_paths for path in requested_paths)
    ):
        raise ValueError("refinement_candidate_binding_invalid")

    baseline_contract_bytes = _baseline_artifact_bytes(
        project, baseline, "experiment/package_contract.json"
    )
    baseline_manifest_bytes = _baseline_artifact_bytes(
        project, baseline, "experiment/package_manifest.json"
    )
    baseline_config_bytes = _baseline_artifact_bytes(
        project, baseline, "experiment/code/config.json"
    )
    baseline_package = manifest.get("baseline_package")
    expected_package = {
        "contract_sha256": _sha256(baseline_contract_bytes),
        "manifest_sha256": _sha256(baseline_manifest_bytes),
        "config_sha256": _sha256(baseline_config_bytes),
    }
    if baseline_package != expected_package:
        raise ValueError("refinement_candidate_binding_invalid")
    try:
        baseline_contract = json.loads(
            baseline_contract_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        baseline_manifest = json.loads(
            baseline_manifest_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        baseline_config = json.loads(
            baseline_config_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("refinement_candidate_baseline_changed") from error
    if not all(
        isinstance(payload, Mapping)
        for payload in (baseline_contract, baseline_manifest, baseline_config)
    ):
        raise ValueError("refinement_candidate_baseline_changed")
    unchanged = manifest.get("unchanged_declarations")
    expected_unchanged = {
        "input_paths": list(baseline.input_paths),
        "input_contract": baseline_config.get("input_contract"),
        "split_strategy": baseline_config.get("split_strategy"),
        "metrics": baseline_contract.get("metrics"),
    }
    if unchanged != expected_unchanged:
        raise ValueError("refinement_candidate_binding_invalid")

    package_contract = manifest.get("package_contract")
    entry_point = manifest.get("entry_point")
    try:
        package_contract = validate_relative_path(
            package_contract, kind="candidate package contract"
        )
        entry_point = validate_relative_path(entry_point, kind="candidate entry point")
    except ValueError as error:
        raise ValueError("refinement_candidate_path_invalid") from error
    prefix = f"refinement/candidates/{candidate_id}/"
    if (
        f"{prefix}{package_contract}" not in reference_paths
        or f"{prefix}{entry_point}" not in reference_paths
        or not package_contract.startswith("package_metadata/")
        or not entry_point.startswith("code/")
    ):
        raise ValueError("refinement_candidate_path_invalid")
    candidate_root = project.root / prefix
    try:
        validated = validate_experiment_package_contract_at(
            project,
            package_root=candidate_root,
            contract_path=package_contract,
        )
    except ValueError as error:
        raise ValueError("refinement_candidate_package_invalid") from error
    if validated.entry_point != entry_point:
        raise ValueError("refinement_candidate_binding_invalid")
    contract_payload, _ = _read_bounded_json(candidate_root / package_contract)
    canonical_sources, semantic_destinations = _canonical_candidate_baseline_sources(
        baseline=baseline,
        baseline_contract=baseline_contract,
        baseline_manifest=baseline_manifest,
        candidate_contract=contract_payload,
        candidate_entry_point=validated.entry_point,
        candidate_self_test_argv=validated.self_test_argv,
        candidate_execution_argv=validated.execution_argv,
        candidate_contract_path=package_contract,
        prefix=prefix,
    )
    baseline_by_path = {str(item["path"]): item for item in baseline.artifacts}
    actual_changed_paths: set[str] = set()
    for candidate_file in candidate_files:
        path = candidate_file.reference.path
        canonical_source = canonical_sources.get(path)
        if canonical_source is None:
            actual_changed_paths.add(path)
            if (
                path in semantic_destinations
                and candidate_file.candidate_only_classification != "self_test_fixture"
            ) or (
                path not in semantic_destinations
                and candidate_file.candidate_only_classification is not None
            ):
                raise ValueError("refinement_candidate_provenance_invalid")
            continue
        if (
            candidate_file.baseline_source_path != canonical_source
            or candidate_file.candidate_only_classification is not None
        ):
            raise ValueError("refinement_candidate_provenance_invalid")
        baseline_item = baseline_by_path[canonical_source]
        if (
            candidate_file.reference.sha256 != baseline_item["sha256"]
            or candidate_file.reference.size != baseline_item["size"]
        ):
            actual_changed_paths.add(path)
    if set(requested_paths) != actual_changed_paths:
        raise ValueError("refinement_candidate_binding_invalid")

    candidate_metrics = contract_payload.get("metrics")
    baseline_metrics = baseline_contract.get("metrics")
    if not isinstance(candidate_metrics, list) or not isinstance(
        baseline_metrics, list
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    normalized_candidate_metrics = [
        {
            **metric,
            "implementation": (
                f"experiment.code.main:{metric['implementation'].partition(':')[2]}"
                if isinstance(metric, Mapping)
                and isinstance(metric.get("implementation"), str)
                else None
            ),
        }
        for metric in candidate_metrics
    ]
    if normalized_candidate_metrics != baseline_metrics:
        raise ValueError("refinement_candidate_binding_invalid")
    config_path = contract_payload.get("config_path")
    if not isinstance(config_path, str):
        raise ValueError("refinement_candidate_binding_invalid")
    candidate_config, _ = _read_bounded_json(candidate_root / config_path)
    candidate_input_contract = candidate_config.get("input_contract")
    if (
        not isinstance(candidate_input_contract, Mapping)
        or candidate_input_contract != baseline_config.get("input_contract")
        or candidate_input_contract.get("required_paths") != list(baseline.input_paths)
        or candidate_config.get("split_strategy")
        != baseline_config.get("split_strategy")
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    candidate_self_test = contract_payload.get("self_test")
    baseline_self_test = baseline_contract.get("self_test")
    if (
        contract_payload.get("dependencies") != baseline_contract.get("dependencies")
        or contract_payload.get("prohibitions") != baseline_contract.get("prohibitions")
        or not isinstance(candidate_self_test, Mapping)
        or not isinstance(baseline_self_test, Mapping)
        or candidate_self_test.get("expected_metrics")
        != baseline_self_test.get("expected_metrics")
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    return (
        references,
        snapshots,
        decision_ref,
        validated.contract_sha256,
        entry_point,
    )


def _candidate_sequence_valid(
    project: ResearchProject, *, candidate_id: str, manifest_path: str
) -> bool:
    registered: list[tuple[int, str]] = []
    for path in project.state.artifacts:
        match = _CANDIDATE_MANIFEST.fullmatch(path)
        if match is not None:
            registered.append((int(match.group(1).split("-")[1]), path))
    registered.sort()
    if [number for number, _ in registered] != list(range(1, len(registered) + 1)):
        return False
    number = int(candidate_id.split("-")[1])
    if any(path == manifest_path for _, path in registered):
        return number <= len(registered)
    return number == len(registered) + 1


def _registered_candidate_statuses(
    project: ResearchProject,
    *,
    session: RefinementSessionStatus,
    baseline: _Baseline,
    unregistered_additional_paths: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[CandidateStatus, ...]:
    unregistered_additional_paths = unregistered_additional_paths or {}
    manifest_entries: list[tuple[int, str, ArtifactRef]] = []
    package_state_paths: dict[str, set[str]] = {}
    report_state_paths: dict[str, tuple[str, ArtifactRef]] = {}
    intent_state_paths: dict[str, tuple[str, ArtifactRef]] = {}
    preparation_state_paths: dict[str, tuple[str, ArtifactRef]] = {}
    registration_state_paths: dict[str, tuple[str, ArtifactRef]] = {}
    for path, reference in project.state.artifacts.items():
        manifest_match = _CANDIDATE_MANIFEST.fullmatch(path)
        if manifest_match is not None:
            candidate_id = manifest_match.group(1)
            manifest_entries.append((int(candidate_id.split("-")[1]), path, reference))
        report_match = _CANDIDATE_SELF_TEST_REPORT.fullmatch(path)
        if (
            report_match is None
            and path.startswith("refinement/candidates/")
            and path.endswith("/package_metadata/self_test_report.json")
        ):
            raise ValueError("refinement_candidate_binding_invalid")
        if report_match is not None:
            report_candidate = report_match.group(1)
            if report_candidate in report_state_paths:
                raise ValueError("refinement_candidate_binding_invalid")
            report_state_paths[report_candidate] = (path, reference)
        file_match = _CANDIDATE_FILE_PATH.fullmatch(path)
        if file_match is not None and manifest_match is None and report_match is None:
            package_state_paths.setdefault(file_match.group(1), set()).add(path)
        intent_match = _CANDIDATE_SELF_TEST_PREPARATION_INTENT.fullmatch(path)
        if intent_match is not None:
            intent_session, intent_candidate = intent_match.groups()
            if (
                intent_session != session.session_id
                or intent_candidate in intent_state_paths
            ):
                raise ValueError("refinement_candidate_binding_invalid")
            intent_state_paths[intent_candidate] = (path, reference)
        preparation_match = _CANDIDATE_SELF_TEST_PREPARATION.fullmatch(path)
        if preparation_match is not None:
            prepared_session, prepared_candidate = preparation_match.groups()
            if (
                prepared_session != session.session_id
                or prepared_candidate in preparation_state_paths
            ):
                raise ValueError("refinement_candidate_binding_invalid")
            preparation_state_paths[prepared_candidate] = (path, reference)
        registration_match = _CANDIDATE_SELF_TEST_REGISTRATION.fullmatch(path)
        if registration_match is not None:
            registered_session, registered_candidate = registration_match.groups()
            if (
                registered_session != session.session_id
                or registered_candidate in registration_state_paths
            ):
                raise ValueError("refinement_candidate_binding_invalid")
            registration_state_paths[registered_candidate] = (path, reference)
        if path.startswith(".researchclaw/refinement-self-tests/") and (
            intent_match is None
            and preparation_match is None
            and registration_match is None
        ):
            raise ValueError("refinement_candidate_binding_invalid")
    manifest_entries.sort()
    if [number for number, _, _ in manifest_entries] != list(
        range(1, len(manifest_entries) + 1)
    ):
        raise ValueError("refinement_candidate_id_invalid")
    manifest_ids = {
        _CANDIDATE_MANIFEST.fullmatch(path).group(1) for _, path, _ in manifest_entries
    }
    if (
        set(package_state_paths) - manifest_ids
        or set(report_state_paths) - manifest_ids
        or set(intent_state_paths) - manifest_ids
        or set(preparation_state_paths) - manifest_ids
        or set(registration_state_paths) - manifest_ids
    ):
        raise ValueError("refinement_candidate_binding_invalid")

    statuses: list[CandidateStatus] = []
    latest_candidate_id = (
        _CANDIDATE_MANIFEST.fullmatch(manifest_entries[-1][1]).group(1)
        if manifest_entries
        else None
    )
    for _, manifest_path, manifest_reference in manifest_entries:
        candidate_id = _CANDIDATE_MANIFEST.fullmatch(manifest_path).group(1)
        manifest_snapshot, manifest_bytes = _secure_snapshot(
            project.root,
            manifest_path,
            expected=manifest_reference,
            maximum_bytes=_MAX_RECORD_BYTES,
            read_payload=True,
            error_code="refinement_candidate_identity_changed",
        )
        try:
            manifest, parsed_bytes = _read_bounded_json(project.root / manifest_path)
        except ValueError as error:
            raise ValueError("refinement_candidate_schema_invalid") from error
        if parsed_bytes != manifest_bytes:
            raise ValueError("refinement_candidate_identity_changed")
        (
            references,
            _snapshots,
            decision_ref,
            package_contract_sha256,
            entry_point,
        ) = _parse_candidate_manifest(
            project,
            manifest_path=manifest_path,
            candidate_id=candidate_id,
            manifest=manifest,
            session=session,
            baseline=baseline,
        )
        expected_state_paths = {reference.path for reference in references}
        if package_state_paths.get(candidate_id, set()) != expected_state_paths or any(
            project.state.artifacts.get(reference.path) != reference
            for reference in references
        ):
            raise ValueError("refinement_candidate_binding_invalid")
        result_path = f"refinement/candidates/{candidate_id}/results.json"
        self_test_report_path = (
            f"refinement/candidates/{candidate_id}/"
            "package_metadata/self_test_report.json"
        )
        additional_paths: list[str] = list(
            unregistered_additional_paths.get(candidate_id, ())
        )
        if any(
            path
            not in {
                result_path,
                self_test_report_path,
            }
            for path in additional_paths
        ):
            raise ValueError("refinement_candidate_binding_invalid")
        result_reference = project.state.artifacts.get(result_path)
        if result_reference is not None:
            _require_identity_budget(
                (*references, result_reference),
                error_code="refinement_candidate_size_invalid",
            )
            _secure_snapshot(
                project.root,
                result_path,
                expected=result_reference,
                maximum_bytes=result_reference.size,
                error_code="refinement_candidate_identity_changed",
            )
            additional_paths.append(result_path)
        report_entry = report_state_paths.get(candidate_id)
        self_test_report_reference = (
            report_entry[1] if report_entry is not None else None
        )
        if report_entry is not None and report_entry[0] != self_test_report_path:
            raise ValueError("refinement_candidate_binding_invalid")
        if self_test_report_reference is not None:
            _require_identity_budget(
                (*references, self_test_report_reference),
                error_code="refinement_candidate_size_invalid",
            )
            _secure_snapshot(
                project.root,
                self_test_report_path,
                expected=self_test_report_reference,
                maximum_bytes=_MAX_RECORD_BYTES,
                error_code="refinement_candidate_identity_changed",
                size_error_code="refinement_candidate_size_invalid",
            )
            additional_paths.append(self_test_report_path)
        preparation_entry = preparation_state_paths.get(candidate_id)
        intent_entry = intent_state_paths.get(candidate_id)
        if intent_entry is not None:
            intent_path, intent_reference = intent_entry
            _secure_snapshot(
                project.root,
                intent_path,
                expected=intent_reference,
                maximum_bytes=_MAX_RECORD_BYTES,
                error_code="refinement_candidate_identity_changed",
                size_error_code="refinement_candidate_size_invalid",
            )
        if preparation_entry is not None:
            preparation_path, preparation_reference = preparation_entry
            _secure_snapshot(
                project.root,
                preparation_path,
                expected=preparation_reference,
                maximum_bytes=_MAX_RECORD_BYTES,
                error_code="refinement_candidate_identity_changed",
                size_error_code="refinement_candidate_size_invalid",
            )
        registration_entry = registration_state_paths.get(candidate_id)
        self_test_state = (
            intent_entry is not None,
            preparation_entry is not None,
            self_test_report_reference is not None,
            registration_entry is not None,
        )
        if self_test_state not in {
            (False, False, False, False),
            (True, False, False, False),
            (True, True, False, False),
            (True, True, True, True),
        }:
            raise ValueError("refinement_candidate_binding_invalid")
        has_registered_self_test = (
            self_test_report_reference is not None and registration_entry is not None
        )
        if candidate_id == latest_candidate_id and (
            (
                project.state.next_action == "prepare_refinement_run"
                and not has_registered_self_test
            )
            or (
                project.state.next_action == "prepare_refinement_self_test"
                and has_registered_self_test
            )
        ):
            raise ValueError("refinement_candidate_binding_invalid")
        if registration_entry is not None:
            registration_path, registration_reference = registration_entry
            _secure_snapshot(
                project.root,
                registration_path,
                expected=registration_reference,
                maximum_bytes=_MAX_RECORD_BYTES,
                error_code="refinement_candidate_identity_changed",
                size_error_code="refinement_candidate_size_invalid",
            )
        if len(additional_paths) != len(set(additional_paths)):
            raise ValueError("refinement_candidate_binding_invalid")
        _require_closed_candidate_tree(
            project.root / "refinement/candidates" / candidate_id,
            manifest_path=manifest_path,
            references=references,
            additional_paths=tuple(additional_paths),
        )
        statuses.append(
            CandidateStatus(
                candidate_id=candidate_id,
                manifest_path=manifest_path,
                manifest_sha256=manifest_snapshot.reference.sha256,
                decision_sha256=decision_ref.sha256,
                package_contract_sha256=package_contract_sha256,
                entry_point=entry_point,
                files=references,
                next_action="prepare_refinement_self_test",
            )
        )
    return tuple(statuses)


def _revalidate_refinement_candidate(
    project: ResearchProject,
    candidate_id: str,
    *,
    unregistered_report_path: str | None = None,
) -> CandidateStatus:
    current = ResearchProject.open_readonly(project.root)
    session = _load_prepared_refinement_session(current)
    baseline = _baseline(current)
    additional = (
        {candidate_id: (unregistered_report_path,)}
        if unregistered_report_path is not None
        else None
    )
    matches = tuple(
        candidate
        for candidate in _registered_candidate_statuses(
            current,
            session=session,
            baseline=baseline,
            unregistered_additional_paths=additional,
        )
        if candidate.candidate_id == candidate_id
    )
    if len(matches) != 1:
        raise ValueError("refinement_candidate_unknown")
    if current.state.next_action not in {
        "prepare_refinement_self_test",
        "prepare_refinement_run",
    }:
        raise ValueError("refinement_candidate_order_invalid")
    return replace(matches[0], next_action=current.state.next_action)


def revalidate_refinement_candidate(
    project: ResearchProject, candidate_id: str
) -> CandidateStatus:
    """Reopen and fully revalidate one exact registered candidate identity."""
    status = _revalidate_refinement_candidate(project, candidate_id)
    if status.next_action == "prepare_refinement_run":
        from .refinement_execution import (
            _revalidate_registered_self_test_semantics,
        )

        _revalidate_registered_self_test_semantics(project, status)
    return status


def _publish_candidate_state(project: ResearchProject, state: ProjectState) -> None:
    """One replaceable publication seam; post-publication verification owns commit."""
    project.persist_state(state)


def _verify_published_candidate_snapshot(
    project: ResearchProject,
    *,
    expected_state: ProjectState,
    baseline: _Baseline,
    baseline_snapshot: tuple[_FileSnapshot, ...],
    candidate_root: Path,
    manifest_path: str,
    manifest_snapshot: _FileSnapshot,
    references: tuple[ArtifactRef, ...],
    candidate_snapshot: tuple[_FileSnapshot, ...],
) -> None:
    published = ResearchProject.open(project.root)
    if published.state != expected_state:
        raise ValueError("refinement_candidate_binding_invalid")
    if not _same_published_baseline_snapshot(
        baseline_snapshot, _baseline_registration_snapshot(published, baseline)
    ):
        raise ValueError("refinement_candidate_baseline_changed")
    current_candidate = tuple(
        _secure_snapshot(
            published.root,
            reference.path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_candidate_identity_changed",
        )[0]
        for reference in references
    )
    current_manifest = _secure_snapshot(
        published.root,
        manifest_path,
        expected=manifest_snapshot.reference,
        maximum_bytes=_MAX_RECORD_BYTES,
        error_code="refinement_candidate_identity_changed",
    )[0]
    if current_candidate != candidate_snapshot or current_manifest != manifest_snapshot:
        raise ValueError("refinement_candidate_identity_changed")
    _require_closed_candidate_tree(
        candidate_root,
        manifest_path=manifest_path,
        references=references,
    )


@project_mutation
def register_refinement_candidate(
    project: ResearchProject, manifest_path: str | Path
) -> CandidateStatus:
    """Register one closed, immutable, decision-bound refinement candidate."""
    current = ResearchProject.open(project.root)
    starting_state = current.state
    relative_manifest, candidate_id, manifest_file = _candidate_manifest_relative_path(
        current, manifest_path
    )
    session = _deliberation_status(current)
    baseline = _baseline(current)
    registered_candidates = _registered_candidate_statuses(
        current, session=_load_prepared_refinement_session(current), baseline=baseline
    )
    registered = tuple(
        status
        for status in registered_candidates
        if status.candidate_id == candidate_id
    )
    if registered:
        if len(registered) != 1 or registered[0].manifest_path != relative_manifest:
            raise ValueError("refinement_candidate_id_invalid")
        return registered[0]
    if (
        session.phase != "awaiting_candidate"
        or session.next_action != "register_refinement_candidate"
    ):
        raise ValueError("refinement_candidate_order_invalid")
    session_payload, _, _, _ = _existing_payloads(current)
    roots = (
        session_payload.get("envelope", {}).get("allowed_change_roots", [])
        if isinstance(session_payload, Mapping)
        and isinstance(session_payload.get("envelope"), Mapping)
        else []
    )
    if not roots or any(
        not _candidate_path_authorized(
            roots,
            f"refinement/candidates/{candidate_id}/{category}/authorized",
        )
        for category in _CANDIDATE_CATEGORIES
    ):
        raise ValueError("refinement_candidate_path_invalid")
    if not _candidate_sequence_valid(
        current, candidate_id=candidate_id, manifest_path=relative_manifest
    ):
        raise ValueError("refinement_candidate_id_invalid")

    manifest_snapshot, manifest_bytes = _secure_snapshot(
        current.root,
        relative_manifest,
        maximum_bytes=_MAX_RECORD_BYTES,
        read_payload=True,
        error_code="refinement_candidate_identity_changed",
        size_error_code="refinement_candidate_schema_invalid",
    )
    if len(manifest_bytes) > _MAX_RECORD_BYTES:
        raise ValueError("refinement_candidate_schema_invalid")
    try:
        manifest, parsed_bytes = _read_bounded_json(manifest_file)
    except ValueError as error:
        raise ValueError("refinement_candidate_schema_invalid") from error
    if parsed_bytes != manifest_bytes:
        raise ValueError("refinement_candidate_identity_changed")
    baseline_before = _baseline_registration_snapshot(current, baseline)
    (
        references,
        candidate_before,
        decision_ref,
        package_contract_sha256,
        entry_point,
    ) = _parse_candidate_manifest(
        current,
        manifest_path=relative_manifest,
        candidate_id=candidate_id,
        manifest=manifest,
        session=session,
        baseline=baseline,
    )
    round_info = _round_path(current, create=False)
    if (
        round_info is None
        or manifest.get("decision", {}).get("path")
        != f"{_DELIBERATIONS_PATH}/{round_info[0]}/decision.json"
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    candidate_root = current.root / "refinement/candidates" / candidate_id
    _require_closed_candidate_tree(
        candidate_root,
        manifest_path=relative_manifest,
        references=references,
    )
    baseline_after = _baseline_registration_snapshot(current, baseline)
    if baseline_after != baseline_before:
        raise ValueError("refinement_candidate_baseline_changed")
    candidate_after = tuple(
        _secure_snapshot(
            current.root,
            reference.path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_candidate_identity_changed",
        )[0]
        for reference in references
    )
    manifest_after, final_manifest_bytes = _secure_snapshot(
        current.root,
        relative_manifest,
        expected=manifest_snapshot.reference,
        maximum_bytes=_MAX_RECORD_BYTES,
        read_payload=True,
        error_code="refinement_candidate_identity_changed",
        size_error_code="refinement_candidate_schema_invalid",
    )
    if (
        candidate_after != candidate_before
        or manifest_after != manifest_snapshot
        or final_manifest_bytes != manifest_bytes
    ):
        raise ValueError("refinement_candidate_identity_changed")
    _require_closed_candidate_tree(
        candidate_root,
        manifest_path=relative_manifest,
        references=references,
    )
    refreshed = ResearchProject.open(current.root)
    if refreshed.state != starting_state:
        raise ValueError("refinement_candidate_binding_invalid")
    published = {reference.path: reference for reference in references} | {
        relative_manifest: manifest_snapshot.reference
    }
    for path, reference in published.items():
        existing = refreshed.state.artifacts.get(path)
        if existing not in {None, reference}:
            raise ValueError("refinement_candidate_identity_changed")
    published_state = replace(
        refreshed.state,
        next_action="prepare_refinement_self_test",
        artifacts={**refreshed.state.artifacts, **published},
    )
    try:
        _publish_candidate_state(refreshed, published_state)
        _verify_published_candidate_snapshot(
            refreshed,
            expected_state=published_state,
            baseline=baseline,
            baseline_snapshot=baseline_before,
            candidate_root=candidate_root,
            manifest_path=relative_manifest,
            manifest_snapshot=manifest_snapshot,
            references=references,
            candidate_snapshot=candidate_before,
        )
    except Exception:
        rollback = ResearchProject.open(refreshed.root)
        if rollback.state != starting_state:
            rollback.persist_state(starting_state)
        raise
    return CandidateStatus(
        candidate_id=candidate_id,
        manifest_path=relative_manifest,
        manifest_sha256=manifest_snapshot.reference.sha256,
        decision_sha256=decision_ref.sha256,
        package_contract_sha256=package_contract_sha256,
        entry_point=entry_point,
        files=references,
        next_action="prepare_refinement_self_test",
    )
