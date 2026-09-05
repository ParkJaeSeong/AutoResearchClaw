"""Development-only validation and registration for Stage-13 candidates."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

from .execution_environment import ExecutionEnvironment, inspect_execution_environment
from .evidence_store import EvidenceSource, EvidenceStore, _native_rename_noreplace
from . import experiment_package_contract as package_contract
from .experiment_package_contract import validate_experiment_package_contract_at
from .models import ArtifactRef, ProjectState
from .project import ResearchProject
from .refinement import (
    EVIDENCE_PACKET_PATH,
    SESSION_PATH,
    CandidateStatus,
    _artifact,
    _baseline,
    _baseline_registration_snapshot,
    _canonical_json,
    _created_at,
    _load_prepared_refinement_session,
    _registered_candidate_statuses,
    _reject_duplicate_keys,
    _revalidate_refinement_candidate,
    _same_published_baseline_snapshot,
    _secure_snapshot,
    revalidate_refinement_candidate,
)
from .transactions import project_mutation
from .research_execution import (
    _validate_result_metrics,
    _validate_result_runtime,
    _validate_result_splits,
)


REFINEMENT_SELF_TEST_REGISTRATION_ROOT = ".researchclaw/refinement-self-tests"
REFINEMENT_RUN_REGISTRATION_ROOT = ".researchclaw/refinement-runs"
REFINEMENT_EVIDENCE_MANIFEST_ROOT = ".researchclaw/evidence/refinement-manifests"
_REPORT_LOCAL_PATH = "package_metadata/self_test_report.json"
_CONTRACT_LOCAL_PATH = "package_metadata/package_contract.json"
_MANIFEST_LOCAL_PATH = "package_metadata/package_manifest.json"
_MAX_JSON_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
_CANDIDATE_ID = re.compile(r"candidate-[0-9]{3}\Z")
_INTENT_ID = re.compile(r"[0-9a-f]{32}\Z")
_RUN_ID = re.compile(r"run-([0-9]{3})\Z")
_RUN_LEAF = re.compile(
    r"(run-[0-9]{3})\.(intent|contract|registration\.intent|registration)\.json\Z"
)
_REPORT_KEYS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "producer_role",
    "created_at",
    "report_created_at",
    "preparation_created_at",
    "preparation",
    "intent_id",
    "intent_created_at",
    "preparation_intent",
    "context_id",
    "context_sha256",
    "candidate_manifest",
    "council_decision",
    "evidence_packet",
    "baseline_manifest",
    "package_contract",
    "fixture",
    "environment_fingerprint",
    "execution_environment",
    "launcher_identity",
    "package_manifest",
    "entry_point",
    "package_files",
    "candidate_files",
    "config",
    "metrics",
    "passed",
    "development_only",
}
_IDENTITY_KEYS = {"path", "sha256"}
_METRIC_KEYS = {"name", "actual", "expected", "tolerance"}
_FILESYSTEM_IDENTITY_KEYS = {
    "device",
    "inode",
    "mode",
    "links",
    "size",
    "mtime_ns",
    "ctime_ns",
}
_RECEIPT_FILESYSTEM_IDENTITY_KEYS = {"device", "inode", "mode", "links"}
_RECEIPT_KEYS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "producer_role",
    "preparation_created_at",
    "report_created_at",
    "preparation",
    "intent_id",
    "intent_created_at",
    "preparation_intent",
    "context_id",
    "context_sha256",
    "candidate_manifest",
    "council_decision",
    "evidence_packet",
    "baseline_manifest",
    "package_contract",
    "package_manifest",
    "candidate_files",
    "entry_point",
    "fixture",
    "config",
    "self_test_report",
    "report_filesystem_identity",
    "receipt_filesystem_identity",
    "environment_fingerprint",
    "execution_environment",
    "launcher_identity",
    "self_test_argv",
    "metrics",
    "passed",
    "development_only",
    "artifacts",
}
_PREPARATION_KEYS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "producer_role",
    "created_at",
    "intent_id",
    "intent_created_at",
    "preparation_intent",
    "candidate_manifest",
    "council_decision",
    "evidence_packet",
    "baseline_manifest",
    "package_contract",
    "package_manifest",
    "candidate_files",
    "entry_point",
    "fixture",
    "config",
    "expected_metrics",
    "self_test_argv",
    "environment_fingerprint",
    "execution_environment",
    "launcher_identity",
    "preparation_filesystem_identity",
    "context_id",
    "context_sha256",
}
_PREPARATION_INTENT_KEYS = {
    "schema_version",
    "intent_id",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "producer_role",
    "created_at",
    "preparation_created_at",
    "preparation_path",
    "report_path",
    "candidate_manifest",
    "council_decision",
    "evidence_packet",
    "baseline_manifest",
    "package_contract",
    "package_manifest",
    "candidate_files",
    "entry_point",
    "fixture",
    "config",
    "expected_metrics",
    "self_test_argv",
    "environment_fingerprint",
    "execution_environment",
    "launcher_identity",
    "intent_filesystem_identity",
}


@dataclass(frozen=True)
class SelfTestPreparationStatus:
    """One verified candidate-rooted self-test command; it is never executed here."""

    candidate_id: str
    argv: tuple[str, ...]
    cwd: str
    environment_fingerprint: str
    environment: ExecutionEnvironment
    launcher_identity: tuple[tuple[object, ...], ...]
    candidate_manifest_sha256: str
    package_contract_sha256: str
    decision_sha256: str
    report_path: str
    preparation_path: str
    intent_path: str
    intent_id: str
    context_id: str
    context_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": "ready_for_explicit_refinement_self_test",
            "candidate_id": self.candidate_id,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "environment_fingerprint": self.environment_fingerprint,
            "environment": {
                "launcher": self.environment.launcher,
                "interpreter": self.environment.interpreter,
                "python_implementation": self.environment.python_implementation,
                "python_version": self.environment.python_version,
                "python_full_version": self.environment.python_full_version,
                "python_build": list(self.environment.python_build),
                "platform": self.environment.platform,
                "machine": self.environment.machine,
                "dependencies": dict(self.environment.dependencies),
                "fingerprint": self.environment.fingerprint,
            },
            "launcher_identity": [list(item) for item in self.launcher_identity],
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "package_contract_sha256": self.package_contract_sha256,
            "decision_sha256": self.decision_sha256,
            "report_path": self.report_path,
            "preparation_path": self.preparation_path,
            "intent_path": self.intent_path,
            "intent_id": self.intent_id,
            "context_id": self.context_id,
            "context_sha256": self.context_sha256,
        }


@dataclass(frozen=True)
class RefinementRunStatus:
    """One reserved Stage-13 run and its exact execution/evidence identity."""

    candidate_id: str
    run_id: str
    argv: tuple[str, ...]
    cwd: str
    environment_fingerprint: str
    intent_path: str
    contract_path: str
    contract_sha256: str
    result_path: str
    evidence_manifest_path: str | None
    runs_used: int
    wall_seconds_used: float
    next_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "environment_fingerprint": self.environment_fingerprint,
            "intent_path": self.intent_path,
            "contract_path": self.contract_path,
            "contract_sha256": self.contract_sha256,
            "result_path": self.result_path,
            "evidence_manifest_path": self.evidence_manifest_path,
            "runs_used": self.runs_used,
            "wall_seconds_used": self.wall_seconds_used,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class _HeldCandidateContext:
    project_id: str
    session_id: str
    producer: str
    producer_role: str
    candidate_manifest: ArtifactRef
    council_decision: ArtifactRef
    evidence_packet: ArtifactRef
    baseline_manifest: ArtifactRef
    manifest_snapshot: object
    bound_snapshots: tuple[object, ...]


@dataclass(frozen=True)
class _ValidatedPreparationIntent:
    reference: ArtifactRef
    snapshot: object
    payload: Mapping[str, object]
    intent_id: str
    created_at: str
    preparation_created_at: str


@dataclass(frozen=True)
class _ValidatedPreparation:
    reference: ArtifactRef
    snapshot: object
    payload: Mapping[str, object]
    intent: ArtifactRef
    intent_id: str
    created_at: str
    context_id: str
    context_sha256: str


def _same_snapshot_with_expected_directory_updates(
    before: object,
    after: object,
    *,
    allowed_ctime_paths: frozenset[str],
) -> bool:
    """Compare held files while allowing ctime from our own directory entry writes."""
    if (
        before.reference != after.reference
        or before.stat_identity != after.stat_identity
    ):
        return False
    if len(before.component_identity) != len(after.component_identity):
        return False
    path_parts: list[str] = []
    for left, right in zip(
        before.component_identity, after.component_identity, strict=True
    ):
        path_parts.append(left[0])
        if left[:3] != right[:3]:
            return False
        if left[3] != right[3] and "/".join(path_parts) not in allowed_ctime_paths:
            return False
    return True


def _same_held_context_with_expected_directory_updates(
    before: _HeldCandidateContext,
    after: _HeldCandidateContext,
    *,
    allowed_ctime_paths: frozenset[str],
) -> bool:
    if (
        before.project_id != after.project_id
        or before.session_id != after.session_id
        or before.producer != after.producer
        or before.producer_role != after.producer_role
        or before.candidate_manifest != after.candidate_manifest
        or before.council_decision != after.council_decision
        or before.evidence_packet != after.evidence_packet
        or before.baseline_manifest != after.baseline_manifest
        or len(before.bound_snapshots) != len(after.bound_snapshots)
    ):
        return False
    return _same_snapshot_with_expected_directory_updates(
        before.manifest_snapshot,
        after.manifest_snapshot,
        allowed_ctime_paths=allowed_ctime_paths,
    ) and all(
        _same_snapshot_with_expected_directory_updates(
            left,
            right,
            allowed_ctime_paths=allowed_ctime_paths,
        )
        for left, right in zip(
            before.bound_snapshots, after.bound_snapshots, strict=True
        )
    )


def _candidate_root(project: ResearchProject, candidate_id: str) -> Path:
    return (
        project.root.resolve(strict=True) / "refinement" / "candidates" / candidate_id
    )


def _parse_held_json(payload: bytes, *, error: str) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        RecursionError,
    ) as exception:
        raise ValueError(error) from exception
    if not isinstance(value, dict):
        raise ValueError(error)
    return value


def _hold_candidate_context(
    project: ResearchProject, candidate: CandidateStatus
) -> _HeldCandidateContext:
    state = project.state
    candidate_manifest = state.artifacts.get(candidate.manifest_path)
    session_reference = state.artifacts.get(SESSION_PATH)
    evidence_packet = state.artifacts.get(EVIDENCE_PACKET_PATH)
    if (
        candidate_manifest is None
        or session_reference is None
        or evidence_packet is None
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    manifest_snapshot, manifest_bytes = _secure_snapshot(
        project.root,
        candidate.manifest_path,
        expected=candidate_manifest,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_candidate_identity_changed",
    )
    manifest = _parse_held_json(
        manifest_bytes, error="refinement_candidate_binding_invalid"
    )
    if manifest_bytes != _canonical_json(manifest):
        raise ValueError("refinement_candidate_binding_invalid")
    try:
        council_decision = _artifact(manifest.get("decision"))
        baseline_manifest = _artifact(manifest.get("baseline_manifest"))
    except ValueError as error:
        raise ValueError("refinement_candidate_binding_invalid") from error
    producer = manifest.get("producer")
    project_id = manifest.get("project_id")
    session_id = manifest.get("session_id")
    if (
        not isinstance(producer, str)
        or not isinstance(project_id, str)
        or not isinstance(session_id, str)
        or project_id != state.project_id
        or candidate_manifest.sha256 != candidate.manifest_sha256
        or council_decision.sha256 != candidate.decision_sha256
        or state.artifacts.get(council_decision.path) != council_decision
        or state.artifacts.get(baseline_manifest.path) != baseline_manifest
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    references = tuple(
        dict.fromkeys(
            (
                candidate_manifest,
                *candidate.files,
                council_decision,
                session_reference,
                evidence_packet,
                baseline_manifest,
            )
        )
    )
    snapshots = tuple(
        _secure_snapshot(
            project.root,
            reference.path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_candidate_identity_changed",
        )[0]
        for reference in references
    )
    if snapshots[0] != manifest_snapshot:
        raise ValueError("refinement_candidate_identity_changed")
    return _HeldCandidateContext(
        project_id=project_id,
        session_id=session_id,
        producer=producer,
        producer_role="implementation",
        candidate_manifest=candidate_manifest,
        council_decision=council_decision,
        evidence_packet=evidence_packet,
        baseline_manifest=baseline_manifest,
        manifest_snapshot=manifest_snapshot,
        bound_snapshots=snapshots,
    )


def _launcher_identity(path: str) -> tuple[tuple[object, ...], ...]:
    try:
        target = Path(path)
        if not target.is_absolute():
            raise ValueError("execution_environment_unavailable")
        identities: list[tuple[object, ...]] = []
        cursor = Path(target.anchor)
        for component in target.parts[1:]:
            cursor /= component
            metadata = cursor.lstat()
            identities.append(
                (
                    component,
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_nlink,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
            )
        target.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    return tuple(identities)


def _inspect_bound_environment(
    package: package_contract.ValidatedExperimentPackage,
) -> tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]]:
    try:
        environment = inspect_execution_environment(
            Path(sys.executable).resolve(strict=True), package.required_distributions
        )
        launcher_identity = _launcher_identity(environment.launcher)
    except (OSError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    return environment, launcher_identity


def _before_refinement_self_test_preparation_final_gate() -> None:
    """Deterministic race seam immediately before preparation's final gate."""


def _after_refinement_self_test_preparation_environment() -> None:
    """Deterministic race seam after final-gate environment inspection."""


def _before_refinement_self_test_publication() -> None:
    """Deterministic race seam immediately before registration's final gate."""


def _before_anchored_registration_leaf_create(*_args: object) -> None:
    """Deterministic race seam after the receipt parent is held open."""


def _after_anchored_registration_write() -> None:
    """Deterministic interruption seam after a complete receipt is durable."""


def _after_anchored_preparation_write() -> None:
    """Deterministic interruption seam before preparation state publication."""


def _after_refinement_self_test_intent_publication() -> None:
    """Deterministic interruption seam after the intent is authoritative."""


def _candidate_context_payload(
    *,
    project: ResearchProject,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
) -> dict[str, object]:
    contract, _contract_bytes = package_contract._read_json_object(
        _candidate_root(project, candidate.candidate_id),
        _CONTRACT_LOCAL_PATH,
        candidate_rooted=True,
    )
    self_test = contract.get("self_test")
    if not isinstance(self_test, Mapping) or not isinstance(
        self_test.get("fixture_path"), str
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    fixture_path = str(self_test["fixture_path"])
    return {
        "project_id": context.project_id,
        "session_id": context.session_id,
        "candidate_id": candidate.candidate_id,
        "producer": context.producer,
        "producer_role": context.producer_role,
        "candidate_manifest": _artifact_payload(context.candidate_manifest),
        "council_decision": _artifact_payload(context.council_decision),
        "evidence_packet": _artifact_payload(context.evidence_packet),
        "baseline_manifest": _artifact_payload(context.baseline_manifest),
        "package_contract": _artifact_payload(
            _candidate_reference(candidate, _CONTRACT_LOCAL_PATH)
        ),
        "package_manifest": _artifact_payload(
            _candidate_reference(candidate, _MANIFEST_LOCAL_PATH)
        ),
        "candidate_files": [
            _artifact_payload(reference) for reference in candidate.files
        ],
        "entry_point": _artifact_payload(
            _candidate_reference(candidate, package.entry_point)
        ),
        "fixture": _artifact_payload(_candidate_reference(candidate, fixture_path)),
        "config": _artifact_payload(
            _candidate_reference(
                candidate,
                package.self_test_argv[package.self_test_argv.index("--config") + 1],
            )
        ),
    }


def _expected_self_test_metrics(
    project: ResearchProject, candidate: CandidateStatus
) -> list[object]:
    contract, _contract_bytes = package_contract._read_json_object(
        _candidate_root(project, candidate.candidate_id),
        _CONTRACT_LOCAL_PATH,
        candidate_rooted=True,
    )
    self_test = contract.get("self_test")
    metrics = (
        self_test.get("expected_metrics") if isinstance(self_test, Mapping) else None
    )
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("refinement_self_test_preparation_invalid")
    return list(metrics)


def _preparation_intent_payload(
    *,
    project: ResearchProject,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
    intent_id: str,
    created_at: str,
    preparation_created_at: str,
    preparation_path: str,
    report_path: str,
    filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "intent_id": intent_id,
        **_candidate_context_payload(
            project=project,
            candidate=candidate,
            context=context,
            package=package,
        ),
        "created_at": created_at,
        "preparation_created_at": preparation_created_at,
        "preparation_path": preparation_path,
        "report_path": report_path,
        "expected_metrics": _expected_self_test_metrics(project, candidate),
        "self_test_argv": list(package.self_test_argv),
        "environment_fingerprint": bound_environment[0].fingerprint,
        "execution_environment": _environment_payload(bound_environment[0]),
        "launcher_identity": [list(item) for item in bound_environment[1]],
        "intent_filesystem_identity": dict(filesystem_identity),
    }


def _preparation_payload(
    intent: _ValidatedPreparationIntent,
    filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    authority = intent.payload
    base = {
        "schema_version": 1,
        "intent_id": intent.intent_id,
        "intent_created_at": intent.created_at,
        "preparation_intent": _artifact_payload(intent.reference),
        **{
            key: authority[key]
            for key in (
                "project_id",
                "session_id",
                "candidate_id",
                "producer",
                "producer_role",
                "candidate_manifest",
                "council_decision",
                "evidence_packet",
                "baseline_manifest",
                "package_contract",
                "package_manifest",
                "candidate_files",
                "entry_point",
                "fixture",
                "config",
                "expected_metrics",
                "self_test_argv",
                "environment_fingerprint",
                "execution_environment",
                "launcher_identity",
            )
        },
        "created_at": intent.preparation_created_at,
        "preparation_filesystem_identity": dict(filesystem_identity),
    }
    digest = hashlib.sha256(_canonical_json(base)).hexdigest()
    return {
        **base,
        "context_id": f"refinement-self-test-{digest[:32]}",
        "context_sha256": digest,
    }


def _external_report_context(
    preparation: _ValidatedPreparation,
) -> dict[str, object]:
    payload = preparation.payload
    context = {
        key: payload[key]
        for key in (
            "project_id",
            "session_id",
            "candidate_id",
            "producer",
            "producer_role",
            "intent_id",
            "intent_created_at",
            "preparation_intent",
            "candidate_manifest",
            "council_decision",
            "evidence_packet",
            "baseline_manifest",
            "package_contract",
            "package_manifest",
            "candidate_files",
            "entry_point",
            "fixture",
            "config",
            "environment_fingerprint",
            "execution_environment",
            "launcher_identity",
            "context_id",
            "context_sha256",
        )
    }
    return context | {
        "preparation_created_at": payload["created_at"],
        "preparation": _artifact_payload(preparation.reference),
    }


def _preparation_path(session_id: str, candidate_id: str) -> str:
    return (
        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
        f"{candidate_id}.preparation.json"
    )


def _preparation_intent_path(session_id: str, candidate_id: str) -> str:
    return (
        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
        f"{candidate_id}.preparation.intent.json"
    )


def _intent_authority_paths(intent_path: str) -> tuple[str, str]:
    stem = hashlib.sha256(intent_path.encode("utf-8")).hexdigest()
    return (
        f".researchclaw/refinement-intent-{stem}.authority.json",
        f".researchclaw/refinement-intent-{stem}.staged",
    )


def _read_intent_authority(
    project: ResearchProject, intent_path: str, *, error_code: str
) -> dict[str, object] | None:
    authority_path, staged_path = _intent_authority_paths(intent_path)
    reference = project.state.artifacts.get(authority_path)
    if reference is None:
        return None
    _, encoded = _secure_snapshot(
        project.root,
        authority_path,
        expected=reference,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code=error_code,
    )
    authority = _parse_held_json(encoded, error=error_code)
    _require_closed(
        authority,
        {"schema_version", "intent_path", "staged_path", "intent"},
        error=error_code,
    )
    if (
        authority["schema_version"] != 1
        or authority["intent_path"] != intent_path
        or authority["staged_path"] != staged_path
        or not isinstance(authority["intent"], dict)
        or encoded != _canonical_json(authority)
    ):
        raise ValueError(error_code)
    return authority["intent"]


def _after_refinement_intent_staged() -> None:
    """Crash seam before any durable acceptance authority."""


def _after_refinement_intent_authority_file() -> None:
    """Crash seam before the complete authority file is anchored in state."""


def _after_refinement_intent_authority_state() -> None:
    """Crash seam after acceptance, before final intent publication."""


def _after_refinement_intent_file_publication() -> None:
    """Crash seam before the final intent reference is registered."""


def _publish_authorized_intent(
    project: ResearchProject,
    *,
    intent_path: str,
    parent_descriptor: int,
    payload_builder: Callable[[dict[str, int]], dict[str, object]],
    error_code: str,
    before_accept: Callable[[], object] | None = None,
) -> tuple[dict[str, object], bytes]:
    """Write ahead exact bytes and inode authority before publishing an intent.

    State anchors only complete authority files. An uncommitted staging attempt
    can be restarted with fresh authority; an already published orphan cannot.
    The native no-replace rename preserves the authenticated single-link inode.
    """
    authority_path, staged_path = _intent_authority_paths(intent_path)
    metadata = EvidenceStore(project.root)._open_directory(
        project.root / ".researchclaw"
    )
    authority_name = Path(authority_path).name
    staged_name = Path(staged_path).name
    try:
        intended = _read_intent_authority(project, intent_path, error_code=error_code)
        if intended is None:
            if os.path.lexists(project.root / intent_path):
                raise ValueError(error_code)
            # These exact private attempt paths grant no authority. Validate
            # regular, unlinked-to-anything-else files before removing them.
            for path, name in (
                (staged_path, staged_name),
                (authority_path, authority_name),
            ):
                if os.path.lexists(project.root / path):
                    snapshot = _secure_snapshot(
                        project.root,
                        path,
                        maximum_bytes=_MAX_JSON_BYTES,
                        error_code=error_code,
                    )[0]
                    held = os.stat(name, dir_fd=metadata, follow_symlinks=False)
                    if _filesystem_identity(snapshot) != {
                        **_receipt_filesystem_identity(held),
                        "size": held.st_size,
                        "mtime_ns": held.st_mtime_ns,
                        "ctime_ns": held.st_ctime_ns,
                    }:
                        raise ValueError(error_code)
                    os.unlink(name, dir_fd=metadata)
            descriptor = os.open(
                staged_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=metadata,
            )
            try:
                intended = payload_builder(
                    _receipt_filesystem_identity(os.fstat(descriptor))
                )
                encoded = _canonical_json(intended)
                if len(encoded) > _MAX_JSON_BYTES:
                    raise ValueError(error_code)
                offset = 0
                while offset < len(encoded):
                    offset += os.write(descriptor, encoded[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(metadata)
            _after_refinement_intent_staged()
            authority = _canonical_json(
                {
                    "schema_version": 1,
                    "intent_path": intent_path,
                    "staged_path": staged_path,
                    "intent": intended,
                }
            )
            if len(authority) > _MAX_JSON_BYTES:
                raise ValueError(error_code)
            descriptor = os.open(
                authority_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=metadata,
            )
            try:
                offset = 0
                while offset < len(authority):
                    offset += os.write(descriptor, authority[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(metadata)
            _after_refinement_intent_authority_file()
            if before_accept is not None:
                before_accept()
            if ResearchProject.open_readonly(project.root).state != project.state:
                raise ValueError(error_code)
            committed_state = replace(
                project.state,
                artifacts={
                    **project.state.artifacts,
                    authority_path: ArtifactRef(
                        authority_path,
                        hashlib.sha256(authority).hexdigest(),
                        len(authority),
                    ),
                },
            )
            project.persist_state(committed_state)
            _after_refinement_intent_authority_state()
            project = ResearchProject.open_readonly(project.root)
            if (
                project.state != committed_state
                or _read_intent_authority(project, intent_path, error_code=error_code)
                != intended
            ):
                raise ValueError(error_code)

        encoded = _canonical_json(intended)
        target_exists = os.path.lexists(project.root / intent_path)
        source_path = intent_path if target_exists else staged_path
        snapshot, payload = _secure_snapshot(
            project.root,
            source_path,
            expected=ArtifactRef(
                source_path, hashlib.sha256(encoded).hexdigest(), len(encoded)
            ),
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code=error_code,
        )
        if (
            payload != encoded
            or intended.get("intent_filesystem_identity")
            != _receipt_filesystem_identity_from_snapshot(snapshot)
            or (target_exists and os.path.lexists(project.root / staged_path))
        ):
            raise ValueError(error_code)
        if not target_exists:
            _native_rename_noreplace(
                metadata, staged_name, parent_descriptor, Path(intent_path).name
            )
            os.fsync(parent_descriptor)
            os.fsync(metadata)
            _after_refinement_intent_file_publication()
        snapshot = _secure_snapshot(
            project.root,
            intent_path,
            expected=ArtifactRef(
                intent_path, hashlib.sha256(encoded).hexdigest(), len(encoded)
            ),
            maximum_bytes=_MAX_JSON_BYTES,
            error_code=error_code,
        )[0]
        if intended.get(
            "intent_filesystem_identity"
        ) != _receipt_filesystem_identity_from_snapshot(snapshot):
            raise ValueError(error_code)
        if ResearchProject.open_readonly(project.root).state != project.state:
            raise ValueError(error_code)
        return intended, encoded
    except OSError as error:
        raise ValueError(error_code) from error
    finally:
        os.close(metadata)


@project_mutation
def prepare_refinement_self_test(
    project: ResearchProject, candidate_id: str
) -> SelfTestPreparationStatus:
    """Return a verified candidate command without executing or reserving a run."""
    current = ResearchProject.open(project.root)
    starting_state = current.state
    candidate = revalidate_refinement_candidate(current, candidate_id)
    context_before = _hold_candidate_context(current, candidate)
    root = _candidate_root(current, candidate_id)
    report_path = _candidate_report_path(candidate_id)
    if os.path.lexists(current.root / report_path):
        raise ValueError("refinement_self_test_report_exists")
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    state_before = _state_file_snapshot(current)[0]
    package = validate_experiment_package_contract_at(
        current,
        package_root=root,
        contract_path="package_metadata/package_contract.json",
    )
    bound_environment = _inspect_bound_environment(package)
    preparation_path = _preparation_path(context_before.session_id, candidate_id)
    intent_path = _preparation_intent_path(context_before.session_id, candidate_id)
    registered_intent = starting_state.artifacts.get(intent_path)
    registered_preparation = starting_state.artifacts.get(preparation_path)
    if registered_preparation is not None and registered_intent is None:
        raise ValueError("refinement_self_test_preparation_invalid")
    if registered_intent is not None and not os.path.lexists(
        current.root / intent_path
    ):
        raise ValueError("refinement_self_test_preparation_invalid")
    if registered_preparation is not None and not os.path.lexists(
        current.root / preparation_path
    ):
        raise ValueError("refinement_self_test_preparation_invalid")

    authority_state = starting_state
    if registered_intent is None:
        if os.path.lexists(current.root / preparation_path):
            raise ValueError("refinement_self_test_preparation_invalid")
        intent_id = uuid4().hex
        intent_created_at = datetime.now(timezone.utc).isoformat()
        preparation_created_at = datetime.now(timezone.utc).isoformat()
        parent = _open_registration_parent(
            current, context_before.session_id, candidate_id
        )
        try:
            intent_payload, intent_bytes = _publish_authorized_intent(
                current,
                intent_path=intent_path,
                parent_descriptor=parent,
                payload_builder=lambda identity: _preparation_intent_payload(
                    project=current,
                    candidate=candidate,
                    context=context_before,
                    package=package,
                    bound_environment=bound_environment,
                    intent_id=intent_id,
                    created_at=intent_created_at,
                    preparation_created_at=preparation_created_at,
                    preparation_path=preparation_path,
                    report_path=report_path,
                    filesystem_identity=identity,
                ),
                error_code="refinement_self_test_preparation_invalid",
            )
        finally:
            os.close(parent)
        current = ResearchProject.open_readonly(current.root)
        starting_state = current.state
        state_before = _state_file_snapshot(current)[0]
        intent_reference = ArtifactRef(
            intent_path,
            hashlib.sha256(intent_bytes).hexdigest(),
            len(intent_bytes),
        )
        intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent_reference,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=bound_environment,
        )
        if intent.payload != intent_payload:
            raise ValueError("refinement_self_test_preparation_invalid")
        checked_candidate = _revalidate_refinement_candidate(current, candidate_id)
        checked_context = _hold_candidate_context(current, checked_candidate)
        checked_package = validate_experiment_package_contract_at(
            current,
            package_root=root,
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        checked_intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent.reference,
            candidate=checked_candidate,
            context=checked_context,
            package=checked_package,
            bound_environment=bound_environment,
        )
        if (
            checked_candidate != candidate
            or not _same_held_context_with_expected_directory_updates(
                context_before,
                checked_context,
                allowed_ctime_paths=frozenset({".researchclaw"}),
            )
            or checked_package != package
            or checked_intent.reference != intent.reference
            or checked_intent.payload != intent.payload
            or not _same_snapshot_with_expected_directory_updates(
                intent.snapshot,
                checked_intent.snapshot,
                allowed_ctime_paths=frozenset(
                    {
                        ".researchclaw",
                        REFINEMENT_SELF_TEST_REGISTRATION_ROOT,
                        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/"
                        f"{context_before.session_id}",
                    }
                ),
            )
            or not _same_published_baseline_snapshot(
                baseline_before, _baseline_registration_snapshot(current, baseline)
            )
            or _direct_baseline_result_snapshot(current) != result_before
            or _inspect_bound_environment(checked_package) != bound_environment
        ):
            raise ValueError("refinement_candidate_identity_changed")
        current_state_snapshot = _state_file_snapshot(current)[0]
        if (
            current_state_snapshot.reference != state_before.reference
            or current_state_snapshot.stat_identity != state_before.stat_identity
            or ResearchProject.open_readonly(current.root).state != starting_state
        ):
            raise ValueError("refinement_self_test_preparation_invalid")
        authority_state = replace(
            starting_state,
            artifacts={**starting_state.artifacts, intent_path: intent.reference},
        )
        current.persist_state(authority_state)

        published_intent_state = ResearchProject.open_readonly(current.root)
        authoritative_candidate = _revalidate_refinement_candidate(
            published_intent_state, candidate_id
        )
        authoritative_context = _hold_candidate_context(
            published_intent_state, authoritative_candidate
        )
        authoritative_package = validate_experiment_package_contract_at(
            published_intent_state,
            package_root=root,
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        authoritative_intent = _read_and_validate_preparation_intent(
            project=published_intent_state,
            path=intent_path,
            expected_reference=intent.reference,
            candidate=authoritative_candidate,
            context=authoritative_context,
            package=authoritative_package,
            bound_environment=bound_environment,
        )
        allowed_state_update = frozenset({".researchclaw"})
        if (
            published_intent_state.state != authority_state
            or authoritative_candidate != candidate
            or not _same_held_context_with_expected_directory_updates(
                context_before,
                authoritative_context,
                allowed_ctime_paths=allowed_state_update,
            )
            or authoritative_package != package
            or authoritative_intent.reference != intent.reference
            or authoritative_intent.payload != intent.payload
            or not _same_snapshot_with_expected_directory_updates(
                intent.snapshot,
                authoritative_intent.snapshot,
                allowed_ctime_paths=allowed_state_update,
            )
            or not _same_published_baseline_snapshot(
                baseline_before,
                _baseline_registration_snapshot(published_intent_state, baseline),
            )
            or _direct_baseline_result_snapshot(published_intent_state) != result_before
            or _inspect_bound_environment(authoritative_package) != bound_environment
        ):
            raise ValueError("refinement_candidate_identity_changed")
        candidate = authoritative_candidate
        context_before = authoritative_context
        package = authoritative_package
        intent = authoritative_intent
        baseline_before = _baseline_registration_snapshot(
            published_intent_state, baseline
        )
        result_before = _direct_baseline_result_snapshot(published_intent_state)
        current = ResearchProject.open(current.root)
        _after_refinement_self_test_intent_publication()
    else:
        intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=registered_intent,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=bound_environment,
        )

    state_before_preparation = _state_file_snapshot(current)[0]
    preparation_exists = os.path.lexists(current.root / preparation_path)
    if preparation_exists:
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=registered_preparation,
            intent=intent,
        )
    else:
        try:
            payload, payload_bytes = _write_anchored_record(
                current,
                session_id=context_before.session_id,
                candidate_id=candidate_id,
                leaf_name=f"{candidate_id}.preparation.json",
                payload_builder=lambda identity: _preparation_payload(intent, identity),
                error_code="refinement_self_test_preparation_invalid",
            )
        except FileExistsError as error:
            raise ValueError("refinement_self_test_preparation_invalid") from error
        preparation_reference = ArtifactRef(
            preparation_path,
            hashlib.sha256(payload_bytes).hexdigest(),
            len(payload_bytes),
        )
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            intent=intent,
        )
        if preparation.payload != payload:
            raise ValueError("refinement_self_test_preparation_invalid")
        _after_anchored_preparation_write()
    target_state = replace(
        authority_state,
        artifacts={
            **authority_state.artifacts,
            preparation_path: preparation.reference,
        },
    )
    if registered_preparation is not None:
        if (
            registered_preparation != preparation.reference
            or target_state != authority_state
        ):
            raise ValueError("refinement_self_test_preparation_invalid")
    else:
        current_state_snapshot = _state_file_snapshot(current)[0]
        if (
            ResearchProject.open_readonly(current.root).state != authority_state
            or current_state_snapshot.reference != state_before_preparation.reference
            or current_state_snapshot.stat_identity
            != state_before_preparation.stat_identity
        ):
            raise ValueError("refinement_self_test_preparation_invalid")
        current.persist_state(target_state)

    try:
        published = ResearchProject.open_readonly(current.root)
        if published.state != target_state:
            raise ValueError("refinement_self_test_preparation_invalid")
        authoritative_candidate = _revalidate_refinement_candidate(
            published, candidate_id
        )
        authoritative_context = _hold_candidate_context(
            published, authoritative_candidate
        )
        authoritative_package = validate_experiment_package_contract_at(
            published,
            package_root=root,
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        authoritative_intent = _read_and_validate_preparation_intent(
            project=published,
            path=intent_path,
            expected_reference=intent.reference,
            candidate=authoritative_candidate,
            context=authoritative_context,
            package=authoritative_package,
            bound_environment=bound_environment,
        )
        authoritative_preparation = _read_and_validate_preparation(
            project=published,
            path=preparation_path,
            expected_reference=preparation.reference,
            intent=authoritative_intent,
        )
        authoritative_baseline = _baseline_registration_snapshot(published, baseline)
        authoritative_result = _direct_baseline_result_snapshot(published)
        allowed_state_update = frozenset({".researchclaw"})
        if (
            authoritative_candidate != candidate
            or not _same_held_context_with_expected_directory_updates(
                context_before,
                authoritative_context,
                allowed_ctime_paths=allowed_state_update,
            )
            or authoritative_package != package
            or authoritative_intent.reference != intent.reference
            or authoritative_intent.payload != intent.payload
            or authoritative_preparation.reference != preparation.reference
            or authoritative_preparation.payload != preparation.payload
            or not _same_snapshot_with_expected_directory_updates(
                preparation.snapshot,
                authoritative_preparation.snapshot,
                allowed_ctime_paths=allowed_state_update,
            )
            or not _same_published_baseline_snapshot(
                baseline_before, authoritative_baseline
            )
            or authoritative_result != result_before
        ):
            raise ValueError("refinement_candidate_identity_changed")
        candidate = authoritative_candidate
        context_before = authoritative_context
        package = authoritative_package
        intent = authoritative_intent
        preparation = authoritative_preparation
        baseline_before = authoritative_baseline
        result_before = authoritative_result
        published_state_snapshot = _state_file_snapshot(published)[0]
        _before_refinement_self_test_preparation_final_gate()
        first_environment = _inspect_bound_environment(package)
        if first_environment != bound_environment:
            raise ValueError("refinement_self_test_environment_changed")
        _after_refinement_self_test_preparation_environment()

        def final_candidate_gate() -> _ValidatedPreparation:
            if os.path.lexists(published.root / report_path):
                raise ValueError("refinement_self_test_report_exists")
            checked_candidate = _revalidate_refinement_candidate(
                published, candidate_id
            )
            checked_context = _hold_candidate_context(published, checked_candidate)
            checked_package = validate_experiment_package_contract_at(
                published,
                package_root=root,
                contract_path=_CONTRACT_LOCAL_PATH,
            )
            checked_intent = _read_and_validate_preparation_intent(
                project=published,
                path=intent_path,
                expected_reference=intent.reference,
                candidate=checked_candidate,
                context=checked_context,
                package=checked_package,
                bound_environment=bound_environment,
            )
            checked_preparation = _read_and_validate_preparation(
                project=published,
                path=preparation_path,
                expected_reference=preparation.reference,
                intent=checked_intent,
            )
            if (
                checked_candidate != candidate
                or checked_context != context_before
                or checked_package != package
                or checked_intent != intent
                or checked_preparation != preparation
                or _baseline_registration_snapshot(published, baseline)
                != baseline_before
                or _direct_baseline_result_snapshot(published) != result_before
                or _state_file_snapshot(published)[0] != published_state_snapshot
                or ResearchProject.open_readonly(published.root).state != target_state
            ):
                raise ValueError("refinement_candidate_identity_changed")
            return checked_preparation

        final_candidate_gate()
        if _inspect_bound_environment(package) != bound_environment:
            raise ValueError("refinement_self_test_environment_changed")
        preparation = final_candidate_gate()
    except Exception:
        if registered_preparation is None:
            rollback = ResearchProject.open(current.root)
            if rollback.state != authority_state:
                rollback.persist_state(authority_state)
        raise
    environment, launcher_identity = bound_environment
    context_argument = _canonical_json(_external_report_context(preparation)).decode(
        "utf-8"
    )
    return SelfTestPreparationStatus(
        candidate_id=candidate_id,
        argv=(
            environment.launcher,
            package.entry_point,
            *package.self_test_argv,
            "--refinement-self-test-context",
            context_argument,
        ),
        cwd=str(root),
        environment_fingerprint=environment.fingerprint,
        environment=environment,
        launcher_identity=launcher_identity,
        candidate_manifest_sha256=candidate.manifest_sha256,
        package_contract_sha256=package.contract_sha256,
        decision_sha256=candidate.decision_sha256,
        report_path=report_path,
        preparation_path=preparation_path,
        intent_path=intent_path,
        intent_id=intent.intent_id,
        context_id=preparation.context_id,
        context_sha256=preparation.context_sha256,
    )


def _artifact_payload(reference: ArtifactRef) -> dict[str, object]:
    return {
        "path": reference.path,
        "sha256": reference.sha256,
        "size": reference.size,
    }


def _environment_payload(environment: ExecutionEnvironment) -> dict[str, object]:
    return {
        "launcher": environment.launcher,
        "interpreter": environment.interpreter,
        "python_implementation": environment.python_implementation,
        "python_version": environment.python_version,
        "python_full_version": environment.python_full_version,
        "python_build": list(environment.python_build),
        "platform": environment.platform,
        "machine": environment.machine,
        "dependencies": dict(environment.dependencies),
        "fingerprint": environment.fingerprint,
    }


def _require_closed(
    value: object, keys: set[str], *, error: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(error)
    return value


def _candidate_report_path(candidate_id: str) -> str:
    return f"refinement/candidates/{candidate_id}/{_REPORT_LOCAL_PATH}"


def _registration_path(session_id: str, candidate_id: str) -> str:
    return f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/{candidate_id}.json"


def _candidate_reference(candidate: CandidateStatus, local_path: str) -> ArtifactRef:
    project_path = f"refinement/candidates/{candidate.candidate_id}/{local_path}"
    matches = tuple(
        reference for reference in candidate.files if reference.path == project_path
    )
    if len(matches) != 1:
        raise ValueError("refinement_candidate_binding_invalid")
    return matches[0]


def _report_artifact(value: object, expected: ArtifactRef) -> None:
    try:
        parsed = _artifact(value)
    except ValueError as error:
        raise ValueError("refinement_self_test_report_invalid") from error
    if parsed != expected:
        raise ValueError("refinement_self_test_report_invalid")


def _report_artifact_list(value: object, expected: tuple[ArtifactRef, ...]) -> None:
    if not isinstance(value, list) or len(value) != len(expected):
        raise ValueError("refinement_self_test_report_invalid")
    for item, reference in zip(value, expected, strict=True):
        _report_artifact(item, reference)


def _report_launcher_identity(
    value: object, expected: tuple[tuple[object, ...], ...]
) -> None:
    if not isinstance(value, list) or len(value) != len(expected):
        raise ValueError("refinement_self_test_report_invalid")
    normalized: list[tuple[object, ...]] = []
    for component in value:
        if (
            not isinstance(component, list)
            or len(component) != 8
            or not isinstance(component[0], str)
            or any(
                isinstance(item, bool) or not isinstance(item, int)
                for item in component[1:]
            )
        ):
            raise ValueError("refinement_self_test_report_invalid")
        normalized.append(tuple(component))
    if tuple(normalized) != expected:
        raise ValueError("refinement_self_test_environment_changed")


def _finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return float("-inf") < float(value) < float("inf")
    except (OverflowError, TypeError):
        return False


def _validate_report_metrics(
    value: object, expected_metrics: object
) -> tuple[dict[str, object], ...]:
    if not isinstance(expected_metrics, list) or not expected_metrics:
        raise ValueError("refinement_self_test_report_invalid")
    expected: dict[str, tuple[float, float]] = {}
    for raw in expected_metrics:
        item = _require_closed(
            raw,
            {"name", "expected", "tolerance"},
            error="refinement_self_test_report_invalid",
        )
        name = item.get("name")
        expected_value = item.get("expected")
        tolerance = item.get("tolerance")
        if (
            not isinstance(name, str)
            or not name
            or name in expected
            or not _finite_number(expected_value)
            or not _finite_number(tolerance)
            or float(tolerance) < 0
        ):
            raise ValueError("refinement_self_test_report_invalid")
        expected[name] = (float(expected_value), float(tolerance))
    if not isinstance(value, list):
        raise ValueError("refinement_self_test_report_invalid")
    reported: list[dict[str, object]] = []
    names: set[str] = set()
    for raw in value:
        metric = _require_closed(
            raw, _METRIC_KEYS, error="refinement_self_test_report_invalid"
        )
        name = metric.get("name")
        if (
            not isinstance(name, str)
            or name in names
            or not all(
                _finite_number(metric.get(field))
                for field in ("actual", "expected", "tolerance")
            )
        ):
            raise ValueError("refinement_self_test_report_invalid")
        names.add(name)
        if name not in expected:
            raise ValueError("refinement_self_test_report_invalid")
        required_expected, required_tolerance = expected[name]
        if (
            float(metric["expected"]) != required_expected
            or float(metric["tolerance"]) != required_tolerance
            or abs(float(metric["actual"]) - required_expected) > required_tolerance
        ):
            raise ValueError("refinement_self_test_report_invalid")
        reported.append(dict(metric))
    if names != set(expected):
        raise ValueError("refinement_self_test_report_invalid")
    return tuple(reported)


@dataclass(frozen=True)
class _ValidatedCandidateSelfTest:
    report: ArtifactRef
    report_snapshot: object
    created_at: str
    environment_fingerprint: str
    package_manifest: ArtifactRef
    entry_point: ArtifactRef
    fixture: ArtifactRef
    config: ArtifactRef
    metrics: tuple[dict[str, object], ...]


def _read_candidate_bytes(
    root: Path, local_path: str, *, maximum_bytes: int = 16 * 1024 * 1024
) -> bytes:
    try:
        return package_contract._read_candidate_package_bytes(
            root, local_path, maximum_bytes=maximum_bytes
        )
    except (OSError, ValueError) as error:
        raise ValueError("refinement_self_test_report_invalid") from error


def _validate_candidate_self_test_report(
    project: ResearchProject,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
    context: _HeldCandidateContext,
    preparation: _ValidatedPreparation,
) -> _ValidatedCandidateSelfTest:
    root = _candidate_root(project, candidate.candidate_id)
    try:
        contract, _contract_bytes = package_contract._read_json_object(
            root, _CONTRACT_LOCAL_PATH, candidate_rooted=True
        )
        package_manifest, manifest_bytes = package_contract._read_json_object(
            root, _MANIFEST_LOCAL_PATH, candidate_rooted=True
        )
        report, report_bytes = package_contract._read_json_object(
            root, _REPORT_LOCAL_PATH, candidate_rooted=True
        )
    except (OSError, ValueError) as error:
        raise ValueError("refinement_self_test_report_invalid") from error
    _require_closed(report, _REPORT_KEYS, error="refinement_self_test_report_invalid")
    if (
        report.get("schema_version") != 1
        or isinstance(report.get("schema_version"), bool)
        or report.get("passed") is not True
        or report.get("development_only") is not True
    ):
        raise ValueError("refinement_self_test_report_invalid")
    try:
        created_at = _created_at(report.get("created_at"))
        report_created_at = _created_at(report.get("report_created_at"))
    except ValueError as error:
        raise ValueError("refinement_self_test_report_invalid") from error
    expected_report_context = _external_report_context(preparation)
    if created_at != report_created_at or any(
        report.get(key) != value for key, value in expected_report_context.items()
    ):
        raise ValueError("refinement_self_test_report_invalid")
    if (
        report.get("project_id") != context.project_id
        or report.get("session_id") != context.session_id
        or report.get("candidate_id") != candidate.candidate_id
        or report.get("producer") != context.producer
        or report.get("producer_role") != context.producer_role
    ):
        raise ValueError("refinement_self_test_report_invalid")
    _report_artifact(report.get("candidate_manifest"), context.candidate_manifest)
    _report_artifact(report.get("council_decision"), context.council_decision)
    _report_artifact(report.get("evidence_packet"), context.evidence_packet)
    _report_artifact(report.get("baseline_manifest"), context.baseline_manifest)
    _report_artifact_list(report.get("candidate_files"), candidate.files)
    package_contract_ref = _candidate_reference(candidate, _CONTRACT_LOCAL_PATH)
    _report_artifact(report.get("package_contract"), package_contract_ref)
    if package_contract_ref.sha256 != package.contract_sha256:
        raise ValueError("refinement_self_test_report_invalid")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    prefix = f"refinement/candidates/{candidate.candidate_id}/"
    package_manifest_ref = ArtifactRef(
        f"{prefix}{_MANIFEST_LOCAL_PATH}", manifest_sha256, len(manifest_bytes)
    )
    _report_artifact(report.get("package_manifest"), package_manifest_ref)
    entry_bytes = _read_candidate_bytes(root, package.entry_point)
    entry_sha256 = hashlib.sha256(entry_bytes).hexdigest()
    entry_ref = ArtifactRef(
        f"{prefix}{package.entry_point}", entry_sha256, len(entry_bytes)
    )
    _report_artifact(report.get("entry_point"), entry_ref)
    files = package_manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("refinement_self_test_report_invalid")
    expected_files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for raw in files:
        if not isinstance(raw, Mapping) or set(raw) - {"path", "role", "sha256"}:
            raise ValueError("refinement_self_test_report_invalid")
        path = raw.get("path")
        digest = raw.get("sha256")
        if (
            not isinstance(path, str)
            or path in seen_paths
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or hashlib.sha256(_read_candidate_bytes(root, path)).hexdigest() != digest
        ):
            raise ValueError("refinement_self_test_report_invalid")
        seen_paths.add(path)
        expected_files.append({"path": path, "sha256": digest})
    reported_files = report.get("package_files")
    if not isinstance(reported_files, list):
        raise ValueError("refinement_self_test_report_invalid")
    normalized_reported: list[dict[str, str]] = []
    for raw in reported_files:
        identity = _require_closed(
            raw, _IDENTITY_KEYS, error="refinement_self_test_report_invalid"
        )
        path = identity.get("path")
        digest = identity.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise ValueError("refinement_self_test_report_invalid")
        normalized_reported.append({"path": path, "sha256": digest})
    if normalized_reported != expected_files:
        raise ValueError("refinement_self_test_report_invalid")
    self_test = contract.get("self_test")
    if not isinstance(self_test, Mapping):
        raise ValueError("refinement_self_test_report_invalid")
    fixture_path = self_test.get("fixture_path")
    if not isinstance(fixture_path, str):
        raise ValueError("refinement_self_test_report_invalid")
    fixture_bytes = _read_candidate_bytes(root, fixture_path)
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    fixture_ref = ArtifactRef(
        f"{prefix}{fixture_path}", fixture_sha256, len(fixture_bytes)
    )
    _report_artifact(report.get("fixture"), fixture_ref)
    fingerprint = report.get("environment_fingerprint")
    if (
        fingerprint != bound_environment[0].fingerprint
        or not isinstance(fingerprint, str)
        or report.get("execution_environment")
        != _environment_payload(bound_environment[0])
    ):
        raise ValueError("refinement_self_test_environment_changed")
    _report_launcher_identity(report.get("launcher_identity"), bound_environment[1])
    argv = self_test.get("argv_suffix")
    if (
        not isinstance(argv, list)
        or argv.count("--config") != 1
        or argv.index("--config") + 1 >= len(argv)
        or not isinstance(argv[argv.index("--config") + 1], str)
    ):
        raise ValueError("refinement_self_test_report_invalid")
    config_path = argv[argv.index("--config") + 1]
    config_bytes = _read_candidate_bytes(root, config_path)
    config_ref = ArtifactRef(
        f"{prefix}{config_path}",
        hashlib.sha256(config_bytes).hexdigest(),
        len(config_bytes),
    )
    _report_artifact(report.get("config"), config_ref)
    metrics = _validate_report_metrics(
        report.get("metrics"), self_test.get("expected_metrics")
    )
    report_path = _candidate_report_path(candidate.candidate_id)
    report_snapshot, secure_report_bytes = _secure_snapshot(
        project.root,
        report_path,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_report_invalid",
    )
    if secure_report_bytes != report_bytes:
        raise ValueError("refinement_self_test_report_invalid")
    return _ValidatedCandidateSelfTest(
        report=report_snapshot.reference,
        report_snapshot=report_snapshot,
        created_at=created_at,
        environment_fingerprint=fingerprint,
        package_manifest=package_manifest_ref,
        entry_point=entry_ref,
        fixture=fixture_ref,
        config=config_ref,
        metrics=metrics,
    )


def _filesystem_identity(snapshot: object) -> dict[str, int]:
    values = snapshot.stat_identity
    return {
        "device": values[0],
        "inode": values[1],
        "mode": values[2],
        "links": values[3],
        "size": values[4],
        "mtime_ns": values[5],
        "ctime_ns": values[6],
    }


def _receipt_filesystem_identity(metadata: os.stat_result) -> dict[str, int]:
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "links": metadata.st_nlink,
    }


def _require_filesystem_identity(
    value: object, *, receipt: bool, error: str
) -> dict[str, int]:
    keys = _RECEIPT_FILESYSTEM_IDENTITY_KEYS if receipt else _FILESYSTEM_IDENTITY_KEYS
    payload = _require_closed(value, keys, error=error)
    if any(
        isinstance(payload.get(key), bool) or not isinstance(payload.get(key), int)
        for key in keys
    ):
        raise ValueError(error)
    return {key: int(payload[key]) for key in keys}


def _open_registration_parent(
    project: ResearchProject, session_id: str, candidate_id: str
) -> int:
    if (
        _SESSION_ID.fullmatch(session_id) is None
        or _CANDIDATE_ID.fullmatch(candidate_id) is None
    ):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(project.root.resolve(strict=True), flags)
        for component in (".researchclaw", "refinement-self-tests", session_id):
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno != errno.ENOENT:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                else:
                    os.fsync(descriptor)
                child = os.open(component, flags, dir_fd=descriptor)
                os.fsync(child)
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise ValueError("refinement_self_test_registration_recovery_invalid")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ValueError) as error:
        if "descriptor" in locals():
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise ValueError(
            "refinement_self_test_registration_recovery_invalid"
        ) from error


def _write_anchored_record(
    project: ResearchProject,
    *,
    session_id: str,
    candidate_id: str,
    leaf_name: str,
    payload_builder,
    before_leaf_create=None,
    error_code: str,
) -> tuple[dict[str, object], bytes]:
    if (
        _SESSION_ID.fullmatch(session_id) is None
        or _CANDIDATE_ID.fullmatch(candidate_id) is None
        or leaf_name
        not in {
            f"{candidate_id}.json",
            f"{candidate_id}.preparation.json",
            f"{candidate_id}.preparation.intent.json",
        }
    ):
        raise ValueError(error_code)
    parent_descriptor = _open_registration_parent(project, session_id, candidate_id)
    descriptor: int | None = None
    try:
        if before_leaf_create is not None:
            before_leaf_create(parent_descriptor, leaf_name)
        descriptor = os.open(
            leaf_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        initial = os.fstat(descriptor)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size != 0
        ):
            raise ValueError(error_code)
        payload = payload_builder(_receipt_filesystem_identity(initial))
        encoded = _canonical_json(payload)
        if len(encoded) > _MAX_JSON_BYTES:
            raise ValueError(error_code)
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if _receipt_filesystem_identity(final) != _receipt_filesystem_identity(
            initial
        ) or final.st_size != len(encoded):
            raise ValueError(error_code)
        os.fsync(parent_descriptor)
        return payload, encoded
    except FileExistsError:
        raise
    except (OSError, ValueError) as error:
        raise ValueError(error_code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_descriptor)


def _write_anchored_registration(
    project: ResearchProject,
    *,
    session_id: str,
    candidate_id: str,
    payload_builder,
) -> tuple[dict[str, object], bytes]:
    return _write_anchored_record(
        project,
        session_id=session_id,
        candidate_id=candidate_id,
        leaf_name=f"{candidate_id}.json",
        payload_builder=payload_builder,
        before_leaf_create=_before_anchored_registration_leaf_create,
        error_code="refinement_self_test_registration_recovery_invalid",
    )


def _read_and_validate_preparation_intent(
    *,
    project: ResearchProject,
    path: str,
    expected_reference: ArtifactRef,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
) -> _ValidatedPreparationIntent:
    """Validate the state-anchored authority from which preparation is derived.

    The local, non-cryptographic trust boundary is the project state plus its
    registered immutable artifact references. Rewriting that authority and every
    bound artifact coherently is outside this validator's tamper-detection model.
    """
    try:
        snapshot, payload_bytes = _secure_snapshot(
            project.root,
            path,
            expected=expected_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_preparation_invalid",
        )
        payload = _parse_held_json(
            payload_bytes, error="refinement_self_test_preparation_invalid"
        )
        _require_closed(
            payload,
            _PREPARATION_INTENT_KEYS,
            error="refinement_self_test_preparation_invalid",
        )
        if (
            payload.get("environment_fingerprint") != bound_environment[0].fingerprint
            or payload.get("execution_environment")
            != _environment_payload(bound_environment[0])
            or payload.get("launcher_identity")
            != [list(item) for item in bound_environment[1]]
        ):
            raise ValueError("refinement_self_test_environment_changed")
        intent_id = payload.get("intent_id")
        if not isinstance(intent_id, str) or _INTENT_ID.fullmatch(intent_id) is None:
            raise ValueError("refinement_self_test_preparation_invalid")
        created_at = _created_at(payload.get("created_at"))
        preparation_created_at = _created_at(payload.get("preparation_created_at"))
        intent_identity = _receipt_filesystem_identity_from_snapshot(snapshot)
        expected = _preparation_intent_payload(
            project=project,
            candidate=candidate,
            context=context,
            package=package,
            bound_environment=bound_environment,
            intent_id=intent_id,
            created_at=created_at,
            preparation_created_at=preparation_created_at,
            preparation_path=_preparation_path(context.session_id, candidate.candidate_id),
            report_path=_candidate_report_path(candidate.candidate_id),
            filesystem_identity=intent_identity,
        )
    except ValueError as error:
        if str(error) == "refinement_self_test_environment_changed":
            raise
        raise ValueError("refinement_self_test_preparation_invalid") from error
    except OSError as error:
        raise ValueError("refinement_self_test_preparation_invalid") from error
    if payload != expected or payload_bytes != _canonical_json(expected):
        raise ValueError("refinement_self_test_preparation_invalid")
    return _ValidatedPreparationIntent(
        reference=snapshot.reference,
        snapshot=snapshot,
        payload=payload,
        intent_id=intent_id,
        created_at=created_at,
        preparation_created_at=preparation_created_at,
    )


def _read_and_validate_preparation(
    *,
    project: ResearchProject,
    path: str,
    expected_reference: ArtifactRef | None,
    intent: _ValidatedPreparationIntent,
) -> _ValidatedPreparation:
    try:
        snapshot, payload_bytes = _secure_snapshot(
            project.root,
            path,
            expected=expected_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_preparation_invalid",
        )
        payload = _parse_held_json(
            payload_bytes, error="refinement_self_test_preparation_invalid"
        )
        _require_closed(
            payload,
            _PREPARATION_KEYS,
            error="refinement_self_test_preparation_invalid",
        )
        preparation_identity = _receipt_filesystem_identity_from_snapshot(snapshot)
        expected = _preparation_payload(intent, preparation_identity)
        created_at = _created_at(payload.get("created_at"))
    except (OSError, ValueError) as error:
        raise ValueError("refinement_self_test_preparation_invalid") from error
    if payload != expected or payload_bytes != _canonical_json(expected):
        raise ValueError("refinement_self_test_preparation_invalid")
    context_id = payload.get("context_id")
    context_sha256 = payload.get("context_sha256")
    if not isinstance(context_id, str) or not isinstance(context_sha256, str):
        raise ValueError("refinement_self_test_preparation_invalid")
    return _ValidatedPreparation(
        reference=snapshot.reference,
        snapshot=snapshot,
        payload=payload,
        intent=intent.reference,
        intent_id=intent.intent_id,
        created_at=created_at,
        context_id=context_id,
        context_sha256=context_sha256,
    )


def _registration_payload(
    *,
    project: ResearchProject,
    session_id: str,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    preparation: _ValidatedPreparation,
    package_contract_ref: ArtifactRef,
    validated: _ValidatedCandidateSelfTest,
    self_test_argv: tuple[str, ...],
    report_filesystem_identity: Mapping[str, int],
    receipt_filesystem_identity: Mapping[str, int],
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    role_references = [
        ("candidate_manifest", context.candidate_manifest),
        ("council_decision", context.council_decision),
        ("evidence_packet", context.evidence_packet),
        ("baseline_manifest", context.baseline_manifest),
        ("self_test_preparation_intent", preparation.intent),
        ("self_test_preparation", preparation.reference),
        *(("candidate_file", reference) for reference in candidate.files),
        ("self_test_report", validated.report),
    ]
    seen: set[str] = set()
    for role, reference in role_references:
        if reference.path in seen:
            continue
        seen.add(reference.path)
        artifacts.append({"role": role, **_artifact_payload(reference)})
    artifacts.sort(key=lambda item: str(item["path"]))
    return {
        "schema_version": 1,
        "project_id": context.project_id,
        "session_id": session_id,
        "candidate_id": candidate.candidate_id,
        "producer": context.producer,
        "producer_role": context.producer_role,
        "intent_id": preparation.intent_id,
        "intent_created_at": preparation.payload["intent_created_at"],
        "preparation_intent": _artifact_payload(preparation.intent),
        "preparation_created_at": preparation.created_at,
        "report_created_at": validated.created_at,
        "preparation": _artifact_payload(preparation.reference),
        "context_id": preparation.context_id,
        "context_sha256": preparation.context_sha256,
        "candidate_manifest": _artifact_payload(context.candidate_manifest),
        "council_decision": _artifact_payload(context.council_decision),
        "evidence_packet": _artifact_payload(context.evidence_packet),
        "baseline_manifest": _artifact_payload(context.baseline_manifest),
        "package_contract": _artifact_payload(package_contract_ref),
        "package_manifest": _artifact_payload(validated.package_manifest),
        "candidate_files": [
            _artifact_payload(reference) for reference in candidate.files
        ],
        "entry_point": _artifact_payload(validated.entry_point),
        "fixture": _artifact_payload(validated.fixture),
        "config": _artifact_payload(validated.config),
        "self_test_report": _artifact_payload(validated.report),
        "report_filesystem_identity": dict(report_filesystem_identity),
        "receipt_filesystem_identity": dict(receipt_filesystem_identity),
        "environment_fingerprint": validated.environment_fingerprint,
        "execution_environment": _environment_payload(bound_environment[0]),
        "launcher_identity": [list(item) for item in bound_environment[1]],
        "self_test_argv": list(self_test_argv),
        "metrics": list(validated.metrics),
        "passed": True,
        "development_only": True,
        "artifacts": artifacts,
    }


def _read_registration(
    project: ResearchProject, relative_path: str
) -> tuple[dict[str, object] | None, bytes | None, object | None]:
    path = project.root / relative_path
    if not os.path.lexists(path):
        return None, None, None
    try:
        snapshot, payload_bytes = _secure_snapshot(
            project.root,
            relative_path,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_registration_recovery_invalid",
        )
        payload = _parse_held_json(
            payload_bytes,
            error="refinement_self_test_registration_recovery_invalid",
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "refinement_self_test_registration_recovery_invalid"
        ) from error
    if snapshot.reference.size != len(payload_bytes):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    return payload, payload_bytes, snapshot


def _publish_refinement_self_test_state(
    project: ResearchProject, state: ProjectState
) -> None:
    """One replaceable state-publication seam for interruption tests."""
    project.persist_state(state)


def _direct_baseline_result_snapshot(project: ResearchProject):
    return _secure_snapshot(
        project.root,
        "experiment/results.json",
        maximum_bytes=16 * 1024 * 1024,
        read_payload=True,
        error_code="refinement_candidate_baseline_changed",
    )


def _state_file_snapshot(project: ResearchProject):
    return _secure_snapshot(
        project.root,
        ".researchclaw/state.json",
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_registration_recovery_invalid",
    )


def _receipt_filesystem_identity_from_snapshot(snapshot: object) -> dict[str, int]:
    values = snapshot.stat_identity
    return {
        "device": values[0],
        "inode": values[1],
        "mode": values[2],
        "links": values[3],
    }


def _validated_receipt(
    *,
    project: ResearchProject,
    session_id: str,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    preparation: _ValidatedPreparation,
    validated: _ValidatedCandidateSelfTest,
    registration_payload: Mapping[str, object],
    registration_bytes: bytes,
    registration_snapshot: object,
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
) -> dict[str, object]:
    _require_closed(
        registration_payload,
        _RECEIPT_KEYS,
        error="refinement_self_test_registration_recovery_invalid",
    )
    receipt_identity = _require_filesystem_identity(
        registration_payload.get("receipt_filesystem_identity"),
        receipt=True,
        error="refinement_self_test_registration_recovery_invalid",
    )
    report_identity = _require_filesystem_identity(
        registration_payload.get("report_filesystem_identity"),
        receipt=False,
        error="refinement_self_test_registration_recovery_invalid",
    )
    current_receipt_identity = _receipt_filesystem_identity_from_snapshot(
        registration_snapshot
    )
    current_report_identity = _filesystem_identity(validated.report_snapshot)
    if (
        receipt_identity != current_receipt_identity
        or report_identity != current_report_identity
    ):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    expected = _registration_payload(
        project=project,
        session_id=session_id,
        candidate=candidate,
        context=context,
        preparation=preparation,
        package_contract_ref=_candidate_reference(candidate, _CONTRACT_LOCAL_PATH),
        validated=validated,
        self_test_argv=package.self_test_argv,
        report_filesystem_identity=current_report_identity,
        receipt_filesystem_identity=current_receipt_identity,
        bound_environment=bound_environment,
    )
    if registration_payload != expected or registration_bytes != _canonical_json(
        expected
    ):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    return expected


def _revalidate_registered_intent_semantics(
    project: ResearchProject, candidate: CandidateStatus
) -> None:
    """Reconstruct one durable preparation intent from registered authorities."""
    try:
        current = ResearchProject.open_readonly(project.root)
        context_before = _hold_candidate_context(current, candidate)
        intent_path = _preparation_intent_path(
            context_before.session_id, candidate.candidate_id
        )
        intent_reference = current.state.artifacts.get(intent_path)
        if intent_reference is None:
            raise ValueError("refinement_candidate_identity_changed")
        package = validate_experiment_package_contract_at(
            current,
            package_root=_candidate_root(current, candidate.candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        environment_before = _inspect_bound_environment(package)
        intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent_reference,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=environment_before,
        )
        context_after = _hold_candidate_context(current, candidate)
        intent_after = _secure_snapshot(
            current.root,
            intent_path,
            expected=intent_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        if (
            context_after != context_before
            or intent_after != intent.snapshot
            or _inspect_bound_environment(package) != environment_before
        ):
            raise ValueError("refinement_candidate_identity_changed")
    except OSError as error:
        raise ValueError("refinement_candidate_identity_changed") from error
    except ValueError as error:
        if str(error) == "refinement_self_test_environment_changed":
            raise
        raise ValueError("refinement_candidate_identity_changed") from error


def _revalidate_registered_preparation_semantics(
    project: ResearchProject, candidate: CandidateStatus
) -> None:
    """Reconstruct one durable preparation from its immutable intent."""
    try:
        current = ResearchProject.open_readonly(project.root)
        context_before = _hold_candidate_context(current, candidate)
        intent_path = _preparation_intent_path(
            context_before.session_id, candidate.candidate_id
        )
        preparation_path = _preparation_path(
            context_before.session_id, candidate.candidate_id
        )
        intent_reference = current.state.artifacts.get(intent_path)
        preparation_reference = current.state.artifacts.get(preparation_path)
        if intent_reference is None or preparation_reference is None:
            raise ValueError("refinement_candidate_identity_changed")
        package = validate_experiment_package_contract_at(
            current,
            package_root=_candidate_root(current, candidate.candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        environment_before = _inspect_bound_environment(package)
        intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent_reference,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=environment_before,
        )
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            intent=intent,
        )
        context_after = _hold_candidate_context(current, candidate)
        intent_after = _secure_snapshot(
            current.root,
            intent_path,
            expected=intent_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        preparation_after = _secure_snapshot(
            current.root,
            preparation_path,
            expected=preparation_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        if (
            context_after != context_before
            or intent_after != intent.snapshot
            or preparation_after != preparation.snapshot
            or _inspect_bound_environment(package) != environment_before
        ):
            raise ValueError("refinement_candidate_identity_changed")
    except OSError as error:
        raise ValueError("refinement_candidate_identity_changed") from error
    except ValueError as error:
        if str(error) == "refinement_self_test_environment_changed":
            raise
        raise ValueError("refinement_candidate_identity_changed") from error


def _revalidate_registered_self_test_semantics(
    project: ResearchProject, candidate: CandidateStatus
) -> None:
    """Reconstruct the registered report and receipt from current authorities."""
    try:
        current = ResearchProject.open_readonly(project.root)
        context_before = _hold_candidate_context(current, candidate)
        registration_path = _registration_path(
            context_before.session_id, candidate.candidate_id
        )
        preparation_path = _preparation_path(
            context_before.session_id, candidate.candidate_id
        )
        intent_path = _preparation_intent_path(
            context_before.session_id, candidate.candidate_id
        )
        report_path = _candidate_report_path(candidate.candidate_id)
        report_reference = current.state.artifacts.get(report_path)
        registration_reference = current.state.artifacts.get(registration_path)
        preparation_reference = current.state.artifacts.get(preparation_path)
        intent_reference = current.state.artifacts.get(intent_path)
        if (
            report_reference is None
            or registration_reference is None
            or preparation_reference is None
            or intent_reference is None
        ):
            raise ValueError("refinement_candidate_identity_changed")
        package = validate_experiment_package_contract_at(
            current,
            package_root=_candidate_root(current, candidate.candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        environment_before = _inspect_bound_environment(package)
        intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent_reference,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=environment_before,
        )
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            intent=intent,
        )
        validated = _validate_candidate_self_test_report(
            current,
            candidate,
            package,
            environment_before,
            context_before,
            preparation,
        )
        if validated.report != report_reference:
            raise ValueError("refinement_candidate_identity_changed")
        registration_snapshot, registration_bytes = _secure_snapshot(
            current.root,
            registration_path,
            expected=registration_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_candidate_identity_changed",
        )
        registration_payload = _parse_held_json(
            registration_bytes, error="refinement_candidate_identity_changed"
        )
        _validated_receipt(
            project=current,
            session_id=context_before.session_id,
            candidate=candidate,
            context=context_before,
            package=package,
            preparation=preparation,
            validated=validated,
            registration_payload=registration_payload,
            registration_bytes=registration_bytes,
            registration_snapshot=registration_snapshot,
            bound_environment=environment_before,
        )
        context_after = _hold_candidate_context(current, candidate)
        report_after = _secure_snapshot(
            current.root,
            report_path,
            expected=report_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        receipt_after = _secure_snapshot(
            current.root,
            registration_path,
            expected=registration_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        preparation_after = _secure_snapshot(
            current.root,
            preparation_path,
            expected=preparation_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        intent_after = _secure_snapshot(
            current.root,
            intent_path,
            expected=intent_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_candidate_identity_changed",
        )[0]
        if (
            context_after != context_before
            or report_after != validated.report_snapshot
            or receipt_after != registration_snapshot
            or preparation_after != preparation.snapshot
            or intent_after != intent.snapshot
            or _inspect_bound_environment(package) != environment_before
        ):
            raise ValueError("refinement_candidate_identity_changed")
    except OSError as error:
        raise ValueError("refinement_candidate_identity_changed") from error
    except ValueError as error:
        if str(error) == "refinement_self_test_environment_changed":
            raise
        raise ValueError("refinement_candidate_identity_changed") from error


@project_mutation
def register_refinement_self_test(
    project: ResearchProject, candidate_id: str, report_path: str | Path
) -> CandidateStatus:
    """Validate and durably register one candidate development self-test."""
    current = ResearchProject.open(project.root)
    expected_report_path = _candidate_report_path(candidate_id)
    supplied_report_path = Path(report_path)
    if supplied_report_path.is_absolute() or supplied_report_path.as_posix() != (
        expected_report_path
    ):
        raise ValueError("refinement_self_test_report_path_invalid")
    starting_state = current.state
    marker_is_complete = starting_state.next_action == "prepare_refinement_run"
    if expected_report_path in starting_state.artifacts and not marker_is_complete:
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    registered_preparations = tuple(
        reference
        for path, reference in starting_state.artifacts.items()
        if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
        and path.endswith(f"/{candidate_id}.preparation.json")
    )
    if len(registered_preparations) == 1 and not os.path.lexists(
        current.root / registered_preparations[0].path
    ):
        raise ValueError("refinement_self_test_preparation_invalid")
    registered_intents = tuple(
        reference
        for path, reference in starting_state.artifacts.items()
        if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
        and path.endswith(f"/{candidate_id}.preparation.intent.json")
    )
    if len(registered_intents) != 1 or not os.path.lexists(
        current.root / registered_intents[0].path
    ):
        raise ValueError("refinement_self_test_preparation_invalid")
    candidate = _revalidate_refinement_candidate(
        current,
        candidate_id,
        unregistered_report_path=None if marker_is_complete else expected_report_path,
    )
    context_before = _hold_candidate_context(current, candidate)
    session_id = context_before.session_id
    registration_path = _registration_path(session_id, candidate_id)
    registered_report = starting_state.artifacts.get(expected_report_path)
    registered_registration = starting_state.artifacts.get(registration_path)
    complete_registration = (
        registered_report is not None
        and registered_registration is not None
        and marker_is_complete
    )
    if (
        any(
            (
                registered_report is not None,
                registered_registration is not None,
                marker_is_complete,
            )
        )
        and not complete_registration
    ):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    if (
        not complete_registration
        and candidate.next_action != "prepare_refinement_self_test"
    ):
        raise ValueError("refinement_self_test_registration_unavailable")
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    state_file_before = _state_file_snapshot(current)
    report_before = _secure_snapshot(
        current.root,
        expected_report_path,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_self_test_report_invalid",
    )[0]
    package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    environment_before = _inspect_bound_environment(package)
    preparation_path = _preparation_path(context_before.session_id, candidate_id)
    intent_path = _preparation_intent_path(context_before.session_id, candidate_id)
    preparation_reference = starting_state.artifacts.get(preparation_path)
    intent_reference = starting_state.artifacts.get(intent_path)
    if preparation_reference is None or intent_reference is None:
        raise ValueError("refinement_self_test_preparation_invalid")
    intent = _read_and_validate_preparation_intent(
        project=current,
        path=intent_path,
        expected_reference=intent_reference,
        candidate=candidate,
        context=context_before,
        package=package,
        bound_environment=environment_before,
    )
    preparation = _read_and_validate_preparation(
        project=current,
        path=preparation_path,
        expected_reference=preparation_reference,
        intent=intent,
    )
    validated = _validate_candidate_self_test_report(
        current,
        candidate,
        package,
        environment_before,
        context_before,
        preparation,
    )
    if _hold_candidate_context(current, candidate) != context_before:
        raise ValueError("refinement_candidate_identity_changed")
    report_after = _secure_snapshot(
        current.root,
        expected_report_path,
        expected=validated.report,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_self_test_report_invalid",
    )[0]
    if report_after != report_before:
        raise ValueError("refinement_self_test_report_invalid")
    if registered_report is not None and registered_report != validated.report:
        raise ValueError("refinement_self_test_report_changed")
    repeated_candidate = _revalidate_refinement_candidate(
        current,
        candidate_id,
        unregistered_report_path=(
            None if complete_registration else expected_report_path
        ),
    )
    if repeated_candidate != candidate:
        raise ValueError("refinement_candidate_identity_changed")
    repeated_package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    if repeated_package != package:
        raise ValueError("refinement_candidate_identity_changed")
    baseline_after_validation = _baseline_registration_snapshot(current, baseline)
    result_after_validation = _direct_baseline_result_snapshot(current)
    if (
        baseline_after_validation != baseline_before
        or result_after_validation != result_before
        or _hold_candidate_context(current, candidate) != context_before
        or _state_file_snapshot(current) != state_file_before
        or ResearchProject.open_readonly(current.root).state != starting_state
    ):
        raise ValueError("refinement_candidate_baseline_changed")

    package_contract_ref = _candidate_reference(candidate, _CONTRACT_LOCAL_PATH)
    if package_contract_ref.sha256 != package.contract_sha256:
        raise ValueError("refinement_candidate_binding_invalid")

    _before_refinement_self_test_publication()
    final_candidate = _revalidate_refinement_candidate(
        current,
        candidate_id,
        unregistered_report_path=(
            None if complete_registration else expected_report_path
        ),
    )
    final_context = _hold_candidate_context(current, final_candidate)
    final_package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    final_intent = _read_and_validate_preparation_intent(
        project=current,
        path=intent_path,
        expected_reference=intent_reference,
        candidate=final_candidate,
        context=final_context,
        package=final_package,
        bound_environment=environment_before,
    )
    final_preparation = _read_and_validate_preparation(
        project=current,
        path=preparation_path,
        expected_reference=preparation_reference,
        intent=final_intent,
    )
    final_report = _secure_snapshot(
        current.root,
        expected_report_path,
        expected=validated.report,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_self_test_report_invalid",
    )[0]
    if (
        final_candidate != candidate
        or final_context != context_before
        or final_package != package
        or final_intent != intent
        or final_preparation != preparation
        or final_report != validated.report_snapshot
        or _baseline_registration_snapshot(current, baseline) != baseline_before
        or _direct_baseline_result_snapshot(current) != result_before
        or _state_file_snapshot(current) != state_file_before
        or ResearchProject.open_readonly(current.root).state != starting_state
    ):
        raise ValueError("refinement_candidate_identity_changed")
    environment_before_publication = _inspect_bound_environment(package)
    if environment_before_publication != environment_before:
        raise ValueError("refinement_self_test_environment_changed")

    existing_payload, existing_bytes, existing_snapshot = _read_registration(
        current, registration_path
    )
    if existing_payload is not None:
        assert existing_bytes is not None and existing_snapshot is not None
        registration_payload = _validated_receipt(
            project=current,
            session_id=session_id,
            candidate=candidate,
            context=context_before,
            package=package,
            preparation=preparation,
            validated=validated,
            registration_payload=existing_payload,
            registration_bytes=existing_bytes,
            registration_snapshot=existing_snapshot,
            bound_environment=environment_before,
        )
        registration_bytes = existing_bytes
    else:
        try:
            registration_payload, registration_bytes = _write_anchored_registration(
                current,
                session_id=session_id,
                candidate_id=candidate_id,
                payload_builder=lambda receipt_identity: _registration_payload(
                    project=current,
                    session_id=session_id,
                    candidate=candidate,
                    context=context_before,
                    preparation=preparation,
                    package_contract_ref=package_contract_ref,
                    validated=validated,
                    self_test_argv=package.self_test_argv,
                    report_filesystem_identity=_filesystem_identity(
                        validated.report_snapshot
                    ),
                    receipt_filesystem_identity=receipt_identity,
                    bound_environment=environment_before,
                ),
            )
        except FileExistsError as error:
            raise ValueError(
                "refinement_self_test_registration_recovery_invalid"
            ) from error
    registration_ref = ArtifactRef(
        registration_path,
        hashlib.sha256(registration_bytes).hexdigest(),
        len(registration_bytes),
    )
    registration_snapshot, persisted_registration_bytes = _secure_snapshot(
        current.root,
        registration_path,
        expected=registration_ref,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_registration_recovery_invalid",
    )
    if persisted_registration_bytes != registration_bytes:
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    refreshed_intent = _read_and_validate_preparation_intent(
        project=current,
        path=intent_path,
        expected_reference=intent_reference,
        candidate=candidate,
        context=context_before,
        package=package,
        bound_environment=environment_before,
    )
    refreshed_preparation = _read_and_validate_preparation(
        project=current,
        path=preparation_path,
        expected_reference=preparation_reference,
        intent=refreshed_intent,
    )
    if (
        refreshed_intent.reference != intent.reference
        or refreshed_intent.payload != intent.payload
        or not _same_snapshot_with_expected_directory_updates(
            intent.snapshot,
            refreshed_intent.snapshot,
            allowed_ctime_paths=frozenset(
                {f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}"}
            ),
        )
        or refreshed_preparation.reference != preparation.reference
        or refreshed_preparation.payload != preparation.payload
        or not _same_snapshot_with_expected_directory_updates(
            preparation.snapshot,
            refreshed_preparation.snapshot,
            allowed_ctime_paths=frozenset(
                {f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/" f"{session_id}"}
            ),
        )
    ):
        raise ValueError("refinement_candidate_identity_changed")
    intent = refreshed_intent
    preparation = refreshed_preparation
    _validated_receipt(
        project=current,
        session_id=session_id,
        candidate=candidate,
        context=context_before,
        package=package,
        preparation=preparation,
        validated=validated,
        registration_payload=registration_payload,
        registration_bytes=registration_bytes,
        registration_snapshot=registration_snapshot,
        bound_environment=environment_before,
    )
    _after_anchored_registration_write()

    def post_write_candidate_gate() -> None:
        checked_candidate = _revalidate_refinement_candidate(
            current,
            candidate_id,
            unregistered_report_path=(
                None if complete_registration else expected_report_path
            ),
        )
        checked_context = _hold_candidate_context(current, checked_candidate)
        checked_package = validate_experiment_package_contract_at(
            current,
            package_root=_candidate_root(current, candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        checked_intent = _read_and_validate_preparation_intent(
            project=current,
            path=intent_path,
            expected_reference=intent_reference,
            candidate=checked_candidate,
            context=checked_context,
            package=checked_package,
            bound_environment=environment_before,
        )
        checked_preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            intent=checked_intent,
        )
        checked_report = _secure_snapshot(
            current.root,
            expected_report_path,
            expected=validated.report,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_self_test_report_invalid",
        )[0]
        checked_registration = _secure_snapshot(
            current.root,
            registration_path,
            expected=registration_ref,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_self_test_registration_recovery_invalid",
        )[0]
        _validated_receipt(
            project=current,
            session_id=session_id,
            candidate=checked_candidate,
            context=checked_context,
            package=checked_package,
            preparation=checked_preparation,
            validated=validated,
            registration_payload=registration_payload,
            registration_bytes=registration_bytes,
            registration_snapshot=checked_registration,
            bound_environment=environment_before,
        )
        if (
            checked_candidate != candidate
            or checked_context != context_before
            or checked_package != package
            or checked_intent != intent
            or checked_preparation != preparation
            or checked_report != validated.report_snapshot
            or checked_registration != registration_snapshot
            or _baseline_registration_snapshot(current, baseline) != baseline_before
            or _direct_baseline_result_snapshot(current) != result_before
            or _state_file_snapshot(current) != state_file_before
            or ResearchProject.open_readonly(current.root).state != starting_state
        ):
            raise ValueError("refinement_candidate_identity_changed")

    post_write_candidate_gate()
    if _inspect_bound_environment(package) != environment_before:
        raise ValueError("refinement_self_test_environment_changed")
    post_write_candidate_gate()

    target_state = replace(
        starting_state,
        next_action="prepare_refinement_run",
        artifacts={
            **starting_state.artifacts,
            expected_report_path: validated.report,
            registration_path: registration_ref,
        },
    )
    if complete_registration:
        if starting_state != target_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    else:
        if ResearchProject.open_readonly(current.root).state != starting_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
        try:
            if _inspect_bound_environment(package) != environment_before:
                raise ValueError("refinement_self_test_environment_changed")
            post_write_candidate_gate()
            _publish_refinement_self_test_state(current, target_state)
            if _inspect_bound_environment(package) != environment_before:
                raise ValueError("refinement_self_test_environment_changed")
        except Exception:
            rollback = ResearchProject.open(current.root)
            if rollback.state != starting_state:
                rollback.persist_state(starting_state)
            raise

    try:
        published = ResearchProject.open_readonly(current.root)
        if published.state != target_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
        final_candidate = revalidate_refinement_candidate(published, candidate_id)
        final_snapshot, final_secure_bytes = _secure_snapshot(
            published.root,
            registration_path,
            expected=registration_snapshot.reference,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_registration_recovery_invalid",
        )
        if (
            final_candidate.next_action != "prepare_refinement_run"
            or final_secure_bytes != registration_bytes
            or not _same_published_baseline_snapshot(
                (registration_snapshot,), (final_snapshot,)
            )
            or not _same_published_baseline_snapshot(
                baseline_before, _baseline_registration_snapshot(published, baseline)
            )
            or _direct_baseline_result_snapshot(published) != result_before
            or _inspect_bound_environment(package) != environment_before
        ):
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    except Exception:
        if not complete_registration:
            rollback = ResearchProject.open(current.root)
            if rollback.state != starting_state:
                rollback.persist_state(starting_state)
        raise
    return final_candidate


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reservation_time(value: object) -> datetime:
    try:
        return datetime.fromisoformat(_created_at(value))
    except ValueError as error:
        raise ValueError("refinement_run_reservation_invalid") from error


def _authoritative_run_wall_seconds(
    contract: Mapping[str, object], observed_at: datetime
) -> float:
    envelope = contract.get("envelope")
    if not isinstance(envelope, Mapping):
        raise ValueError("refinement_run_reservation_invalid")
    reserved_maximum = envelope.get("reserved_maximum_seconds")
    if (
        isinstance(reserved_maximum, bool)
        or not isinstance(reserved_maximum, int)
        or reserved_maximum <= 0
    ):
        raise ValueError("refinement_run_reservation_invalid")
    reservation_created_at = _reservation_time(
        envelope.get("reservation_created_at")
    )
    session_deadline = _reservation_time(envelope.get("session_deadline"))
    if observed_at < reservation_created_at:
        raise ValueError("refinement_run_reservation_invalid")
    if (
        observed_at
        >= reservation_created_at + timedelta(seconds=reserved_maximum)
        or observed_at >= session_deadline
    ):
        raise ValueError("refinement_run_wall_time_exhausted")
    return (observed_at - reservation_created_at).total_seconds()


def _run_intent_path(session_id: str, run_id: str) -> str:
    return f"{REFINEMENT_RUN_REGISTRATION_ROOT}/{session_id}/{run_id}.intent.json"


def _run_contract_path(session_id: str, run_id: str) -> str:
    return f"{REFINEMENT_RUN_REGISTRATION_ROOT}/{session_id}/{run_id}.contract.json"


def _run_result_path(candidate_id: str) -> str:
    return f"refinement/candidates/{candidate_id}/results.json"


def _run_directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("refinement_run_reservation_invalid")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_run_parent_with_identity(
    project: ResearchProject, session_id: str, *, create: bool
) -> tuple[int, tuple[tuple[str, tuple[int, ...]], ...]]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ValueError("refinement_run_reservation_invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(project.root.resolve(strict=True), flags)
        component_identity = [
            (".", _run_directory_identity(os.fstat(descriptor)))
        ]
        for component in (".researchclaw", "refinement-runs", session_id):
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno != errno.ENOENT or not create:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                else:
                    os.fsync(descriptor)
                child = os.open(component, flags, dir_fd=descriptor)
                os.fsync(child)
            metadata = os.fstat(child)
            component_identity.append(
                (component, _run_directory_identity(metadata))
            )
            os.close(descriptor)
            descriptor = child
        return descriptor, tuple(component_identity)
    except (OSError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise ValueError("refinement_run_reservation_invalid") from error


def _open_run_parent(project: ResearchProject, session_id: str) -> int:
    return _open_run_parent_with_identity(project, session_id, create=True)[0]


def _write_run_record(
    project: ResearchProject,
    *,
    session_id: str,
    leaf_name: str,
    payload_builder,
    error_code: str,
) -> tuple[dict[str, object], bytes]:
    match = _RUN_LEAF.fullmatch(leaf_name)
    if match is None:
        raise ValueError(error_code)
    parent = _open_run_parent(project, session_id)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            leaf_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent,
        )
        initial = os.fstat(descriptor)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size != 0
        ):
            raise ValueError(error_code)
        payload = payload_builder(_receipt_filesystem_identity(initial))
        encoded = _canonical_json(payload)
        if len(encoded) > _MAX_JSON_BYTES:
            raise ValueError(error_code)
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if (
            _receipt_filesystem_identity(final)
            != _receipt_filesystem_identity(initial)
            or final.st_size != len(encoded)
        ):
            raise ValueError(error_code)
        os.fsync(parent)
        return payload, encoded
    except FileExistsError:
        raise
    except (OSError, ValueError) as error:
        raise ValueError(error_code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _run_inventory_from_names(
    session_id: str, names: list[str]
) -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    if len(names) > 40:
        raise ValueError("refinement_run_reservation_invalid")
    for name in names:
        match = _RUN_LEAF.fullmatch(name)
        if match is None:
            raise ValueError("refinement_run_reservation_invalid")
        run_id, kind = match.groups()
        if kind in inventory.setdefault(run_id, {}):
            raise ValueError("refinement_run_reservation_invalid")
        inventory[run_id][kind] = (
            f"{REFINEMENT_RUN_REGISTRATION_ROOT}/{session_id}/{name}"
        )
    numbered = sorted(int(run_id.split("-")[1]) for run_id in inventory)
    if numbered != list(range(1, len(numbered) + 1)) or any(
        "intent" not in records for records in inventory.values()
    ):
        raise ValueError("refinement_run_reservation_invalid")
    return {run_id: inventory[run_id] for run_id in sorted(inventory)}


def _run_leaf_snapshot(
    parent: int, name: str, relative_path: str
) -> tuple[ArtifactRef, tuple[object, ...]]:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        initial = os.fstat(descriptor)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size > _MAX_JSON_BYTES
        ):
            raise ValueError("refinement_run_reservation_invalid")
        identity = (
            initial.st_dev,
            initial.st_ino,
            initial.st_mode,
            initial.st_nlink,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        )
        digest = hashlib.sha256()
        total_size = 0
        while True:
            read_size = min(64 * 1024, _MAX_JSON_BYTES - total_size + 1)
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > _MAX_JSON_BYTES:
                raise ValueError("refinement_run_reservation_invalid")
            digest.update(chunk)
        final = os.fstat(descriptor)
        final_identity = (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        )
        if identity != final_identity or total_size != initial.st_size:
            raise ValueError("refinement_run_reservation_invalid")
        return ArtifactRef(relative_path, digest.hexdigest(), total_size), identity
    except (OSError, ValueError) as error:
        raise ValueError("refinement_run_reservation_invalid") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _run_inventory_names(parent: int) -> list[str]:
    with os.scandir(parent) as entries:
        return sorted(entry.name for entry in entries)


def _run_inventory_snapshot(
    project: ResearchProject, session_id: str
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, tuple[ArtifactRef, tuple[object, ...]]],
]:
    root = project.root / REFINEMENT_RUN_REGISTRATION_ROOT / session_id
    if not os.path.lexists(root):
        return {}, {}
    parent, component_identity_before = _open_run_parent_with_identity(
        project, session_id, create=False
    )
    reopened: int | None = None
    verified: int | None = None
    identities: dict[str, tuple[ArtifactRef, tuple[object, ...]]] = {}
    try:
        directory_identity_before = _run_directory_identity(os.fstat(parent))
        names_before = _run_inventory_names(parent)
        inventory = _run_inventory_from_names(session_id, names_before)
        for records in inventory.values():
            for path in records.values():
                name = Path(path).name
                identities[path] = _run_leaf_snapshot(parent, name, path)
        names_after = _run_inventory_names(parent)
        reopened, component_identity_mid = _open_run_parent_with_identity(
            project, session_id, create=False
        )
        reopened_names = _run_inventory_names(reopened)
        directory_identity_after = _run_directory_identity(os.fstat(parent))
        reopened_identity = _run_directory_identity(os.fstat(reopened))
        verified, component_identity_after = _open_run_parent_with_identity(
            project, session_id, create=False
        )
        verified_identity = _run_directory_identity(os.fstat(verified))
        if (
            names_before != names_after
            or names_after != reopened_names
            or directory_identity_before != directory_identity_after
            or directory_identity_after != reopened_identity
            or reopened_identity != verified_identity
            or component_identity_before != component_identity_mid
            or component_identity_before != component_identity_after
        ):
            raise ValueError("refinement_run_reservation_invalid")
        return inventory, identities
    except (OSError, ValueError) as error:
        raise ValueError("refinement_run_reservation_invalid") from error
    finally:
        if verified is not None:
            os.close(verified)
        if reopened is not None:
            os.close(reopened)
        os.close(parent)


def _run_inventory(project: ResearchProject, session_id: str) -> dict[str, dict[str, str]]:
    return _run_inventory_snapshot(project, session_id)[0]


def _assert_closed_run_inventory(
    project: ResearchProject,
    session_id: str,
    *,
    expected_inventory: Mapping[str, Mapping[str, str]],
    expected_identities: Mapping[str, tuple[ArtifactRef, tuple[object, ...]]],
) -> None:
    actual_inventory, actual_identities = _run_inventory_snapshot(project, session_id)
    if actual_inventory != expected_inventory or actual_identities != expected_identities:
        raise ValueError("refinement_run_reservation_invalid")


def _completed_run_wall_seconds(
    project: ResearchProject, inventory: Mapping[str, Mapping[str, str]]
) -> float:
    total = 0.0
    for run_id, records in inventory.items():
        registration_path = records.get("registration")
        if registration_path is None:
            continue
        receipt, _receipt_bytes, _receipt_snapshot = _read_run_payload(
            project,
            registration_path,
            error_code="refinement_evidence_registration_invalid",
        )
        contract_path = records.get("contract")
        if contract_path is None:
            raise ValueError("refinement_evidence_registration_invalid")
        contract, _contract_bytes, _contract_snapshot = _read_run_payload(
            project,
            contract_path,
            error_code="refinement_run_contract_invalid",
        )
        try:
            observed_at = _reservation_time(receipt.get("created_at"))
            elapsed = _authoritative_run_wall_seconds(contract, observed_at)
        except ValueError as error:
            raise ValueError("refinement_evidence_registration_invalid") from error
        if receipt.get("run_id") != run_id or receipt.get("completed") is not True:
            raise ValueError("refinement_evidence_registration_invalid")
        total += elapsed
    return total


def _current_session_payload(project: ResearchProject) -> dict[str, object]:
    _load_prepared_refinement_session(project)
    reference = project.state.artifacts.get(SESSION_PATH)
    if reference is None:
        raise ValueError("refinement_run_reservation_invalid")
    _snapshot, payload_bytes = _secure_snapshot(
        project.root,
        SESSION_PATH,
        expected=reference,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_run_reservation_invalid",
    )
    payload = _parse_held_json(
        payload_bytes, error="refinement_run_reservation_invalid"
    )
    if payload_bytes != _canonical_json(payload):
        raise ValueError("refinement_run_reservation_invalid")
    return payload


def _run_authority_payload(
    project: ResearchProject,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[ExecutionEnvironment, tuple[tuple[object, ...], ...]],
    *,
    session_payload: Mapping[str, object],
    run_id: str,
    contract_path: str,
    runs_reserved_before: int,
    wall_seconds_used_before: float,
    reservation_time: datetime | None,
) -> dict[str, object]:
    baseline = _baseline(project)
    envelope = session_payload.get("envelope")
    if not isinstance(envelope, Mapping):
        raise ValueError("refinement_run_reservation_invalid")
    maximum_runs = envelope.get("maximum_runs")
    maximum_wall_seconds = envelope.get("maximum_wall_seconds")
    maximum_candidate_seconds = envelope.get("maximum_candidate_seconds")
    allowed_change_roots = envelope.get("allowed_change_roots")
    if (
        not isinstance(maximum_runs, int)
        or isinstance(maximum_runs, bool)
        or not isinstance(maximum_wall_seconds, int)
        or isinstance(maximum_wall_seconds, bool)
        or not isinstance(maximum_candidate_seconds, int)
        or isinstance(maximum_candidate_seconds, bool)
        or not isinstance(allowed_change_roots, list)
    ):
        raise ValueError("refinement_run_reservation_invalid")
    session_created_at = datetime.fromisoformat(
        _created_at(session_payload.get("created_at"))
    )
    deadline = session_created_at + timedelta(seconds=maximum_wall_seconds)
    remaining = maximum_wall_seconds - wall_seconds_used_before
    if runs_reserved_before >= maximum_runs:
        raise ValueError("refinement_run_budget_exhausted")
    if remaining <= 0:
        raise ValueError("refinement_run_wall_time_exhausted")
    input_items: list[dict[str, object]] = []
    for input_path in baseline.input_paths:
        item = next(
            entry for entry in baseline.artifacts if entry["path"] == input_path
        )
        reference = ArtifactRef(input_path, str(item["sha256"]), int(item["size"]))
        _secure_snapshot(
            project.root,
            input_path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_run_input_changed",
        )
        input_items.append(_artifact_payload(reference))
    baseline_result_item = next(
        item for item in baseline.artifacts if item["path"] == "experiment/results.json"
    )
    baseline_result = ArtifactRef(
        "experiment/results.json",
        str(baseline_result_item["sha256"]),
        int(baseline_result_item["size"]),
    )
    _secure_snapshot(
        project.root,
        baseline_result.path,
        expected=baseline_result,
        maximum_bytes=baseline_result.size,
        error_code="refinement_candidate_baseline_changed",
    )
    self_test_paths = {
        "intent": _preparation_intent_path(context.session_id, candidate.candidate_id),
        "preparation": _preparation_path(context.session_id, candidate.candidate_id),
        "report": _candidate_report_path(candidate.candidate_id),
        "receipt": _registration_path(context.session_id, candidate.candidate_id),
    }
    self_test: dict[str, object] = {}
    self_test_references: list[ArtifactRef] = []
    for name, path in self_test_paths.items():
        reference = project.state.artifacts.get(path)
        if reference is None:
            raise ValueError("refinement_run_self_test_invalid")
        _secure_snapshot(
            project.root,
            path,
            expected=reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_run_self_test_invalid",
        )
        self_test[name] = _artifact_payload(reference)
        self_test_references.append(reference)
    environment, launcher_identity = bound_environment
    argv = (
        environment.launcher,
        package.entry_point,
        *package.execution_argv,
        "--refinement-run-context",
        str((project.root / contract_path).resolve()),
    )
    package_contract_reference = _candidate_reference(candidate, _CONTRACT_LOCAL_PATH)
    package_manifest_reference = _candidate_reference(candidate, _MANIFEST_LOCAL_PATH)
    entry_point_reference = _candidate_reference(candidate, package.entry_point)
    session_reference = project.state.artifacts.get(SESSION_PATH)
    if session_reference is None:
        raise ValueError("refinement_run_reservation_invalid")
    identity_references: dict[str, ArtifactRef] = {}
    for reference in (
        session_reference,
        context.candidate_manifest,
        *candidate.files,
        package_contract_reference,
        package_manifest_reference,
        entry_point_reference,
        *self_test_references,
        context.council_decision,
        context.evidence_packet,
        context.baseline_manifest,
        baseline_result,
        *(ArtifactRef(str(item["path"]), str(item["sha256"]), int(item["size"])) for item in input_items),
    ):
        prior = identity_references.get(reference.path)
        if prior not in {None, reference}:
            raise ValueError("refinement_run_reservation_invalid")
        identity_references[reference.path] = reference
    binding_filesystem_identities: list[dict[str, object]] = []
    for path in sorted(identity_references):
        reference = identity_references[path]
        snapshot = _secure_snapshot(
            project.root,
            path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_run_binding_changed",
        )[0]
        binding_filesystem_identities.append(
            {"path": path, **_filesystem_identity(snapshot)}
        )
    effective_reservation_time = (
        reservation_time
        if reservation_time is not None
        else _reservation_time(_utc_now().isoformat())
    )
    deadline_seconds_remaining = (
        deadline - effective_reservation_time
    ).total_seconds()
    if deadline_seconds_remaining <= 0:
        raise ValueError("refinement_run_wall_time_exhausted")
    reserved_maximum = min(
        maximum_candidate_seconds,
        int(remaining),
        int(deadline_seconds_remaining),
    )
    if reserved_maximum <= 0:
        raise ValueError("refinement_run_wall_time_exhausted")
    return {
        "project_id": context.project_id,
        "session_id": context.session_id,
        "candidate_id": candidate.candidate_id,
        "run_id": run_id,
        "producer": context.producer,
        "producer_role": context.producer_role,
        "candidate_manifest": _artifact_payload(context.candidate_manifest),
        "candidate_files": [
            _artifact_payload(reference) for reference in candidate.files
        ],
        "package_contract": _artifact_payload(package_contract_reference),
        "package_manifest": _artifact_payload(package_manifest_reference),
        "entry_point": _artifact_payload(entry_point_reference),
        "self_test": self_test,
        "council_decision": _artifact_payload(context.council_decision),
        "evidence_packet": _artifact_payload(context.evidence_packet),
        "baseline_manifest": _artifact_payload(context.baseline_manifest),
        "baseline_result": _artifact_payload(baseline_result),
        "allowed_inputs": input_items,
        "allowed_change_roots": list(allowed_change_roots),
        "binding_filesystem_identities": binding_filesystem_identities,
        "execution": {
            "argv": list(argv),
            "cwd": str(_candidate_root(project, candidate.candidate_id)),
            "run_contract_path": contract_path,
            "input_bindings": [
                {
                    **item,
                    "absolute_path": str((project.root / str(item["path"])).resolve()),
                }
                for item in input_items
            ],
            "environment_fingerprint": environment.fingerprint,
            "environment": _environment_payload(environment),
            "launcher_identity": [list(item) for item in launcher_identity],
        },
        "envelope": {
            "maximum_runs": maximum_runs,
            "maximum_wall_seconds": maximum_wall_seconds,
            "maximum_candidate_seconds": maximum_candidate_seconds,
            "runs_reserved_before": runs_reserved_before,
            "wall_seconds_used_before": wall_seconds_used_before,
            "remaining_wall_seconds": remaining,
            "reservation_created_at": effective_reservation_time.isoformat(),
            "deadline_seconds_remaining": deadline_seconds_remaining,
            "reserved_maximum_seconds": reserved_maximum,
            "session_deadline": deadline.isoformat(),
        },
    }


def _run_intent_payload(
    authority: Mapping[str, object],
    *,
    reservation_id: str,
    created_at: str,
    contract_created_at: str,
    contract_path: str,
    result_path: str,
    filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reservation_id": reservation_id,
        "created_at": created_at,
        "contract_created_at": contract_created_at,
        "contract_path": contract_path,
        "result_path": result_path,
        **dict(authority),
        "intent_filesystem_identity": dict(filesystem_identity),
    }


def _run_contract_payload(
    intent: Mapping[str, object],
    intent_reference: ArtifactRef,
    contract_filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    authority_keys = {
        "project_id",
        "session_id",
        "candidate_id",
        "run_id",
        "producer",
        "producer_role",
        "candidate_manifest",
        "candidate_files",
        "package_contract",
        "package_manifest",
        "entry_point",
        "self_test",
        "council_decision",
        "evidence_packet",
        "baseline_manifest",
        "baseline_result",
        "allowed_inputs",
        "allowed_change_roots",
        "binding_filesystem_identities",
        "execution",
        "envelope",
    }
    contract: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "",
        "created_at": intent["contract_created_at"],
        "reservation": {
            "reservation_id": intent["reservation_id"],
            **_artifact_payload(intent_reference),
        },
        "contract_filesystem_identity": dict(contract_filesystem_identity),
        **{key: intent[key] for key in authority_keys},
        "expected_result": {
            "path": intent["result_path"],
            "schema_version": 1,
            "status": "completed",
            "required_fields": [
                "schema_version",
                "project_id",
                "session_id",
                "candidate_id",
                "run_id",
                "producer",
                "producer_role",
                "created_at",
                "execution_contract",
                "development_only",
                "evidence_eligible",
                "status",
                "metrics",
                "split_summary",
                "provenance",
                "runtime",
            ],
        },
    }
    contract["contract_id"] = hashlib.sha256(
        _canonical_json({key: value for key, value in contract.items() if key != "contract_id"})
    ).hexdigest()
    return contract


def _read_run_payload(
    project: ResearchProject, path: str, *, error_code: str
) -> tuple[dict[str, object], bytes, object]:
    snapshot, payload_bytes = _secure_snapshot(
        project.root,
        path,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code=error_code,
    )
    payload = _parse_held_json(payload_bytes, error=error_code)
    if payload_bytes != _canonical_json(payload):
        raise ValueError(error_code)
    return payload, payload_bytes, snapshot


def _validate_run_intent(
    payload: Mapping[str, object],
    snapshot: object,
    *,
    authority: Mapping[str, object],
    contract_path: str,
    result_path: str,
) -> None:
    expected_keys = {
        "schema_version",
        "reservation_id",
        "created_at",
        "contract_created_at",
        "contract_path",
        "result_path",
        *authority.keys(),
        "intent_filesystem_identity",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 1
        or isinstance(payload.get("schema_version"), bool)
        or not isinstance(payload.get("reservation_id"), str)
        or _INTENT_ID.fullmatch(str(payload.get("reservation_id"))) is None
        or payload.get("contract_path") != contract_path
        or payload.get("result_path") != result_path
        or any(payload.get(key) != value for key, value in authority.items())
    ):
        raise ValueError("refinement_run_reservation_invalid")
    try:
        _created_at(payload.get("created_at"))
        _created_at(payload.get("contract_created_at"))
    except ValueError as error:
        raise ValueError("refinement_run_reservation_invalid") from error
    identity = _require_filesystem_identity(
        payload.get("intent_filesystem_identity"),
        receipt=True,
        error="refinement_run_reservation_invalid",
    )
    if identity != _receipt_filesystem_identity_from_snapshot(snapshot):
        raise ValueError("refinement_run_reservation_invalid")


def _after_refinement_run_intent_publication() -> None:
    """Interruption seam after the run slot becomes durable authority."""


def _after_refinement_run_contract_write() -> None:
    """Interruption seam after the exact contract is durable, before state."""


@project_mutation
def prepare_refinement_run(
    project: ResearchProject, candidate_id: str
) -> RefinementRunStatus:
    """Reserve one bounded candidate run and return its command without executing it."""
    current = ResearchProject.open(project.root)
    session_payload = _current_session_payload(current)
    session_id = str(session_payload["session_id"])
    inventory, expected_run_identities = _run_inventory_snapshot(
        current, session_id
    )
    expected_inventory = {
        run_id: dict(records) for run_id, records in inventory.items()
    }
    session_status = _load_prepared_refinement_session(current)
    candidate_statuses = _registered_candidate_statuses(
        current, session=session_status, baseline=_baseline(current)
    )
    _runs_used, completed_wall_seconds = _reconstruct_refinement_run_counters(
        current, candidate_statuses
    )
    envelope = session_payload.get("envelope")
    if not isinstance(envelope, Mapping):
        raise ValueError("refinement_run_reservation_invalid")
    maximum_runs = envelope.get("maximum_runs")
    maximum_wall_seconds = envelope.get("maximum_wall_seconds")
    latest_is_pending = bool(inventory) and "registration" not in inventory[sorted(inventory)[-1]]
    if not latest_is_pending:
        if (
            not isinstance(maximum_runs, int)
            or isinstance(maximum_runs, bool)
            or len(inventory) >= maximum_runs
        ):
            raise ValueError("refinement_run_budget_exhausted")
        if (
            not isinstance(maximum_wall_seconds, int)
            or isinstance(maximum_wall_seconds, bool)
            or completed_wall_seconds >= maximum_wall_seconds
        ):
            raise ValueError("refinement_run_wall_time_exhausted")
        session_deadline = _reservation_time(session_payload.get("created_at")) + (
            timedelta(seconds=maximum_wall_seconds)
        )
        if _utc_now() >= session_deadline:
            raise ValueError("refinement_run_wall_time_exhausted")
    if current.state.next_action not in {
        "prepare_refinement_run",
        "register_refinement_result",
    }:
        raise ValueError("refinement_run_unavailable")
    if inventory:
        active_run_id = sorted(inventory)[-1]
        active = inventory[active_run_id]
        if "registration" not in active:
            run_id = active_run_id
        else:
            run_id = f"run-{len(inventory) + 1:03d}"
    else:
        run_id = "run-001"
    intent_path = _run_intent_path(session_id, run_id)
    contract_path = _run_contract_path(session_id, run_id)
    result_path = _run_result_path(candidate_id)
    records = inventory.get(run_id, {})
    if records:
        reservation_time: datetime | None = _reservation_time(
            _read_run_payload(
                current,
                intent_path,
                error_code="refinement_run_reservation_invalid",
            )[0].get("created_at")
        )
    else:
        reservation_time = None
    candidate = _revalidate_refinement_candidate(current, candidate_id)
    _revalidate_registered_self_test_semantics(current, candidate)
    context = _hold_candidate_context(current, candidate)
    package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    bound_environment = _inspect_bound_environment(package)
    wall_seconds_used = completed_wall_seconds
    authority = _run_authority_payload(
        current,
        candidate,
        context,
        package,
        bound_environment,
        session_payload=session_payload,
        run_id=run_id,
        contract_path=contract_path,
        runs_reserved_before=(
            int(run_id.split("-")[1]) - 1 if run_id in inventory else len(inventory)
        ),
        wall_seconds_used_before=wall_seconds_used,
        reservation_time=reservation_time,
    )
    intent_reference = current.state.artifacts.get(intent_path)
    contract_reference = current.state.artifacts.get(contract_path)
    if records and records.get("intent") != intent_path:
        raise ValueError("refinement_run_reservation_invalid")
    if records:
        intent_payload, intent_bytes, intent_snapshot = _read_run_payload(
            current, intent_path, error_code="refinement_run_reservation_invalid"
        )
        _validate_run_intent(
            intent_payload,
            intent_snapshot,
            authority=authority,
            contract_path=contract_path,
            result_path=result_path,
        )
        actual_intent_ref = ArtifactRef(
            intent_path, hashlib.sha256(intent_bytes).hexdigest(), len(intent_bytes)
        )
        if intent_reference not in {None, actual_intent_ref}:
            raise ValueError("refinement_run_reservation_invalid")
        if intent_reference is None:
            current.persist_state(
                replace(
                    current.state,
                    artifacts={**current.state.artifacts, intent_path: actual_intent_ref},
                )
            )
            current = ResearchProject.open(current.root)
        intent_reference = actual_intent_ref
    else:
        reservation_id = uuid4().hex
        authority_envelope = authority.get("envelope")
        if not isinstance(authority_envelope, Mapping):
            raise ValueError("refinement_run_reservation_invalid")
        created_at = str(authority_envelope.get("reservation_created_at"))
        try:
            intent_payload, intent_bytes = _write_run_record(
                current,
                session_id=session_id,
                leaf_name=f"{run_id}.intent.json",
                payload_builder=lambda identity: _run_intent_payload(
                    authority,
                    reservation_id=reservation_id,
                    created_at=created_at,
                    contract_created_at=_utc_now().isoformat(),
                    contract_path=contract_path,
                    result_path=result_path,
                    filesystem_identity=identity,
                ),
                error_code="refinement_run_reservation_invalid",
            )
        except FileExistsError as error:
            raise ValueError("refinement_run_reservation_invalid") from error
        intent_reference = ArtifactRef(
            intent_path, hashlib.sha256(intent_bytes).hexdigest(), len(intent_bytes)
        )
        _intent_payload, _intent_bytes, intent_snapshot = _read_run_payload(
            current, intent_path, error_code="refinement_run_reservation_invalid"
        )
        _validate_run_intent(
            intent_payload,
            intent_snapshot,
            authority=authority,
            contract_path=contract_path,
            result_path=result_path,
        )
        current.persist_state(
            replace(
                current.state,
                artifacts={**current.state.artifacts, intent_path: intent_reference},
            )
        )
        current = ResearchProject.open(current.root)
        _after_refinement_run_intent_publication()
    current_intent_identity = (
        intent_snapshot.reference,
        intent_snapshot.stat_identity,
    )
    prior_intent_identity = expected_run_identities.get(intent_path)
    if prior_intent_identity not in {None, current_intent_identity}:
        raise ValueError("refinement_run_reservation_invalid")
    expected_run_identities[intent_path] = current_intent_identity
    expected_inventory.setdefault(run_id, {})["intent"] = intent_path
    _assert_closed_run_inventory(
        current,
        session_id,
        expected_inventory=expected_inventory,
        expected_identities=expected_run_identities,
    )
    if os.path.lexists(current.root / contract_path):
        persisted_contract, contract_bytes, contract_snapshot = _read_run_payload(
            current, contract_path, error_code="refinement_run_contract_invalid"
        )
        contract_payload = _run_contract_payload(
            intent_payload,
            intent_reference,
            _receipt_filesystem_identity_from_snapshot(contract_snapshot),
        )
        expected_contract_bytes = _canonical_json(contract_payload)
        if persisted_contract != contract_payload or contract_bytes != expected_contract_bytes:
            raise ValueError("refinement_run_contract_invalid")
    else:
        try:
            persisted_contract, contract_bytes = _write_run_record(
                current,
                session_id=session_id,
                leaf_name=f"{run_id}.contract.json",
                payload_builder=lambda identity: _run_contract_payload(
                    intent_payload, intent_reference, identity
                ),
                error_code="refinement_run_contract_invalid",
            )
        except FileExistsError as error:
            raise ValueError("refinement_run_contract_invalid") from error
        contract_snapshot = _read_run_payload(
            current, contract_path, error_code="refinement_run_contract_invalid"
        )[2]
        contract_payload = _run_contract_payload(
            intent_payload,
            intent_reference,
            _receipt_filesystem_identity_from_snapshot(contract_snapshot),
        )
        expected_contract_bytes = _canonical_json(contract_payload)
        if persisted_contract != contract_payload or contract_bytes != expected_contract_bytes:
            raise ValueError("refinement_run_contract_invalid")
        _after_refinement_run_contract_write()
    current_contract_identity = (
        contract_snapshot.reference,
        contract_snapshot.stat_identity,
    )
    prior_contract_identity = expected_run_identities.get(contract_path)
    if prior_contract_identity not in {None, current_contract_identity}:
        raise ValueError("refinement_run_contract_invalid")
    expected_run_identities[contract_path] = current_contract_identity
    expected_inventory[run_id]["contract"] = contract_path
    _assert_closed_run_inventory(
        current,
        session_id,
        expected_inventory=expected_inventory,
        expected_identities=expected_run_identities,
    )
    contract_reference = ArtifactRef(
        contract_path, hashlib.sha256(contract_bytes).hexdigest(), len(contract_bytes)
    )
    if current.state.artifacts.get(contract_path) not in {None, contract_reference}:
        raise ValueError("refinement_run_contract_invalid")
    target_state = replace(
        current.state,
        next_action="register_refinement_result",
        artifacts={**current.state.artifacts, contract_path: contract_reference},
    )
    if current.state != target_state:
        current.persist_state(target_state)
    published = ResearchProject.open_readonly(current.root)
    _revalidate_registered_self_test_semantics(published, candidate)
    checked_intent, checked_intent_bytes, checked_intent_snapshot = _read_run_payload(
        published, intent_path, error_code="refinement_run_reservation_invalid"
    )
    _validate_run_intent(
        checked_intent,
        checked_intent_snapshot,
        authority=authority,
        contract_path=contract_path,
        result_path=result_path,
    )
    checked_contract, checked_contract_bytes, checked_contract_snapshot = (
        _read_run_payload(
            published, contract_path, error_code="refinement_run_contract_invalid"
        )
    )
    if (
        published.state != target_state
        or checked_intent_bytes != intent_bytes
        or checked_contract != contract_payload
        or checked_contract
        != _run_contract_payload(
            checked_intent,
            intent_reference,
            _receipt_filesystem_identity_from_snapshot(checked_contract_snapshot),
        )
        or checked_contract_bytes != contract_bytes
        or _inspect_bound_environment(package) != bound_environment
        or os.path.lexists(published.root / result_path)
    ):
        raise ValueError("refinement_run_contract_invalid")
    _assert_closed_run_inventory(
        published,
        session_id,
        expected_inventory=expected_inventory,
        expected_identities=expected_run_identities,
    )
    execution = contract_payload["execution"]
    assert isinstance(execution, Mapping)
    return RefinementRunStatus(
        candidate_id=candidate_id,
        run_id=run_id,
        argv=tuple(str(item) for item in execution["argv"]),
        cwd=str(execution["cwd"]),
        environment_fingerprint=str(execution["environment_fingerprint"]),
        intent_path=intent_path,
        contract_path=contract_path,
        contract_sha256=contract_reference.sha256,
        result_path=result_path,
        evidence_manifest_path=None,
        runs_used=len(inventory) if records else len(inventory) + 1,
        wall_seconds_used=wall_seconds_used,
        next_action="register_refinement_result",
    )


_RESULT_FIELDS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "run_id",
    "producer",
    "producer_role",
    "created_at",
    "execution_contract",
    "development_only",
    "evidence_eligible",
    "status",
    "metrics",
    "split_summary",
    "provenance",
    "runtime",
}
_RESULT_CONTRACT_FIELDS = {"path", "contract_id", "sha256", "size"}
_RESULT_PROVENANCE_FIELDS = {
    "candidate_manifest",
    "candidate_files",
    "package_contract",
    "package_manifest",
    "entry_point",
    "self_test",
    "council_decision",
    "evidence_packet",
    "baseline_manifest",
    "baseline_result",
    "inputs",
    "environment_fingerprint",
    "execution_environment",
    "launcher_identity",
}


def _registration_intent_path(session_id: str, run_id: str) -> str:
    return (
        f"{REFINEMENT_RUN_REGISTRATION_ROOT}/{session_id}/"
        f"{run_id}.registration.intent.json"
    )


def _run_registration_path(session_id: str, run_id: str) -> str:
    return (
        f"{REFINEMENT_RUN_REGISTRATION_ROOT}/{session_id}/"
        f"{run_id}.registration.json"
    )


def _refinement_manifest_path(
    session_id: str, candidate_id: str, run_id: str
) -> str:
    return (
        f"{REFINEMENT_EVIDENCE_MANIFEST_ROOT}/{session_id}/"
        f"{candidate_id}/{run_id}.json"
    )


def _result_expected_provenance(contract: Mapping[str, object]) -> dict[str, object]:
    execution = contract.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("refinement_run_contract_invalid")
    return {
        "candidate_manifest": contract["candidate_manifest"],
        "candidate_files": contract["candidate_files"],
        "package_contract": contract["package_contract"],
        "package_manifest": contract["package_manifest"],
        "entry_point": contract["entry_point"],
        "self_test": contract["self_test"],
        "council_decision": contract["council_decision"],
        "evidence_packet": contract["evidence_packet"],
        "baseline_manifest": contract["baseline_manifest"],
        "baseline_result": contract["baseline_result"],
        "inputs": contract["allowed_inputs"],
        "environment_fingerprint": execution["environment_fingerprint"],
        "execution_environment": execution["environment"],
        "launcher_identity": execution["launcher_identity"],
    }


def _candidate_isolation_key(
    project: ResearchProject,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
) -> str:
    try:
        config_path = package.execution_argv[
            package.execution_argv.index("--config") + 1
        ]
        config, _config_bytes = package_contract._read_json_object(
            _candidate_root(project, candidate.candidate_id),
            config_path,
            candidate_rooted=True,
        )
        split = config.get("split_strategy")
        isolation_key = split.get("isolation_key") if isinstance(split, Mapping) else None
    except (IndexError, OSError, ValueError) as error:
        raise ValueError("refinement_result_split_invalid") from error
    if not isinstance(isolation_key, str) or not isolation_key:
        raise ValueError("refinement_result_split_invalid")
    return isolation_key


def _validate_refinement_result_payload(
    project: ResearchProject,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    *,
    run_id: str,
    contract_path: str,
    contract: Mapping[str, object],
    contract_bytes: bytes,
    result_path: str,
) -> tuple[dict[str, object], bytes, object, float]:
    snapshot, result_bytes = _secure_snapshot(
        project.root,
        result_path,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_result_file_invalid",
    )
    payload = _parse_held_json(result_bytes, error="refinement_result_schema_invalid")
    if set(payload) != _RESULT_FIELDS:
        raise ValueError("refinement_result_schema_invalid")
    if (
        payload.get("schema_version") != 1
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("project_id") != project.state.project_id
        or payload.get("session_id") != contract.get("session_id")
        or payload.get("candidate_id") != candidate.candidate_id
        or payload.get("run_id") != run_id
        or payload.get("producer") != contract.get("producer")
        or payload.get("producer_role") != "implementation"
        or payload.get("status") != "completed"
        or payload.get("development_only") is not False
        or payload.get("evidence_eligible") is not True
    ):
        raise ValueError("refinement_result_schema_invalid")
    try:
        _created_at(payload.get("created_at"))
    except ValueError as error:
        raise ValueError("refinement_result_schema_invalid") from error
    result_contract = payload.get("execution_contract")
    expected_contract = {
        "path": contract_path,
        "contract_id": contract.get("contract_id"),
        "sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "size": len(contract_bytes),
    }
    if (
        not isinstance(result_contract, Mapping)
        or set(result_contract) != _RESULT_CONTRACT_FIELDS
        or dict(result_contract) != expected_contract
    ):
        raise ValueError("refinement_result_contract_mismatch")
    provenance = payload.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or set(provenance) != _RESULT_PROVENANCE_FIELDS
        or dict(provenance) != _result_expected_provenance(contract)
    ):
        raise ValueError("refinement_result_provenance_mismatch")
    try:
        _validate_result_metrics(payload.get("metrics"))
    except ValueError as error:
        raise ValueError("refinement_result_metrics_invalid") from error
    try:
        _validate_result_splits(
            payload.get("split_summary"),
            _candidate_isolation_key(project, candidate, package),
        )
    except ValueError as error:
        if str(error) == "research_result_leakage_detected":
            raise ValueError("refinement_result_leakage_detected") from error
        raise ValueError("refinement_result_split_invalid") from error
    envelope = contract.get("envelope")
    approved = (
        envelope.get("reserved_maximum_seconds")
        if isinstance(envelope, Mapping)
        else None
    )
    try:
        _validate_result_runtime(payload.get("runtime"), approved)
    except ValueError as error:
        raise ValueError("refinement_result_runtime_invalid") from error
    runtime = payload["runtime"]
    if not isinstance(runtime, Mapping) or runtime.get("maximum_seconds") != approved:
        raise ValueError("refinement_result_runtime_invalid")
    elapsed = runtime.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)):
        raise ValueError("refinement_result_runtime_invalid")
    try:
        canonical_result = _canonical_json(payload)
    except ValueError as error:
        raise ValueError("refinement_result_schema_invalid") from error
    if result_bytes != canonical_result:
        raise ValueError("refinement_result_schema_invalid")
    return payload, result_bytes, snapshot, float(elapsed)


def _evidence_sources(
    contract: Mapping[str, object],
    *,
    contract_path: str,
    contract_bytes: bytes,
    result_path: str,
    result_bytes: bytes,
) -> tuple[EvidenceSource, ...]:
    sources: list[EvidenceSource] = [
        EvidenceSource(
            "result",
            result_path,
            hashlib.sha256(result_bytes).hexdigest(),
            len(result_bytes),
        ),
        EvidenceSource(
            "execution_contract",
            contract_path,
            hashlib.sha256(contract_bytes).hexdigest(),
            len(contract_bytes),
        ),
    ]

    def add(role: str, value: object) -> None:
        reference = _artifact(value)
        sources.append(
            EvidenceSource(role, reference.path, reference.sha256, reference.size)
        )

    add("candidate_manifest", contract["candidate_manifest"])
    for item in contract["candidate_files"]:
        add("candidate_file", item)
    add("package_contract", contract["package_contract"])
    add("package_manifest", contract["package_manifest"])
    add("entry_point", contract["entry_point"])
    self_test = contract["self_test"]
    if not isinstance(self_test, Mapping):
        raise ValueError("refinement_result_provenance_mismatch")
    for name in ("intent", "preparation", "report", "receipt"):
        add(f"self_test_{name}", self_test[name])
    add("council_decision", contract["council_decision"])
    add("evidence_packet", contract["evidence_packet"])
    add("baseline_manifest", contract["baseline_manifest"])
    add("baseline_result", contract["baseline_result"])
    for item in contract["allowed_inputs"]:
        add("input", item)
    unique: dict[tuple[str, str], EvidenceSource] = {}
    for source in sources:
        key = (source.role, source.path)
        prior = unique.get(key)
        if prior not in {None, source}:
            raise ValueError("refinement_result_provenance_mismatch")
        unique[key] = source
    return tuple(unique.values())


def _registration_intent_payload(
    *,
    contract: Mapping[str, object],
    registration_id: str,
    created_at: str,
    manifest_created_at: str,
    contract_reference: ArtifactRef,
    result_reference: ArtifactRef,
    result_filesystem_identity: Mapping[str, int],
    sources: tuple[EvidenceSource, ...],
    manifest_path: str,
    filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "registration_id": registration_id,
        "project_id": contract["project_id"],
        "session_id": contract["session_id"],
        "candidate_id": contract["candidate_id"],
        "run_id": contract["run_id"],
        "producer": contract["producer"],
        "producer_role": contract["producer_role"],
        "created_at": created_at,
        "manifest_created_at": manifest_created_at,
        "execution_contract": _artifact_payload(contract_reference),
        "result": _artifact_payload(result_reference),
        "result_filesystem_identity": dict(result_filesystem_identity),
        "sources": [
            {
                "role": source.role,
                "path": source.path,
                "sha256": source.expected_sha256,
                "size": source.expected_size,
            }
            for source in sources
        ],
        "manifest_path": manifest_path,
        "intent_filesystem_identity": dict(filesystem_identity),
    }


def _manifest_payload(
    registration_intent: Mapping[str, object],
    result_payload: Mapping[str, object],
) -> dict[str, object]:
    sources = registration_intent["sources"]
    assert isinstance(sources, list)
    result_entry = next(item for item in sources if item["role"] == "result")
    return {
        "schema_version": 1,
        "registration_id": registration_intent["registration_id"],
        "project_id": registration_intent["project_id"],
        "session_id": registration_intent["session_id"],
        "candidate_id": registration_intent["candidate_id"],
        "run_id": registration_intent["run_id"],
        "producer": registration_intent["producer"],
        "producer_role": registration_intent["producer_role"],
        "created_at": registration_intent["manifest_created_at"],
        "execution_contract": registration_intent["execution_contract"],
        "result": {
            **result_entry,
            "object_path": (
                f".researchclaw/evidence/objects/{result_entry['sha256']}"
            ),
        },
        "objects": [
            {
                "role": item["role"],
                "source_path": item["path"],
                "sha256": item["sha256"],
                "size": item["size"],
                "object_path": f".researchclaw/evidence/objects/{item['sha256']}",
            }
            for item in sources
        ],
        "metrics": result_payload["metrics"],
        "split_summary": result_payload["split_summary"],
        "runtime": result_payload["runtime"],
    }


def _open_refinement_manifest_parent(
    project: ResearchProject, session_id: str, candidate_id: str
) -> int:
    if (
        _SESSION_ID.fullmatch(session_id) is None
        or _CANDIDATE_ID.fullmatch(candidate_id) is None
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(project.root.resolve(strict=True), flags)
        for component in (
            ".researchclaw",
            "evidence",
            "refinement-manifests",
            session_id,
            candidate_id,
        ):
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno != errno.ENOENT:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                else:
                    os.fsync(descriptor)
                child = os.open(component, flags, dir_fd=descriptor)
                os.fsync(child)
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise ValueError("refinement_evidence_registration_invalid")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise ValueError("refinement_evidence_registration_invalid") from error


def _write_refinement_manifest(
    project: ResearchProject,
    *,
    session_id: str,
    candidate_id: str,
    run_id: str,
    payload: Mapping[str, object],
) -> tuple[ArtifactRef, bytes]:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("refinement_evidence_registration_invalid")
    encoded = _canonical_json(payload)
    parent = _open_refinement_manifest_parent(project, session_id, candidate_id)
    name = f"{run_id}.json"
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent,
            )
        except FileExistsError:
            relative = _refinement_manifest_path(session_id, candidate_id, run_id)
            snapshot, existing = _secure_snapshot(
                project.root,
                relative,
                maximum_bytes=_MAX_JSON_BYTES,
                read_payload=True,
                error_code="refinement_evidence_registration_invalid",
            )
            if existing != encoded:
                raise ValueError("refinement_evidence_registration_invalid")
            return snapshot.reference, existing
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if not stat.S_ISREG(final.st_mode) or final.st_nlink != 1:
            raise ValueError("refinement_evidence_registration_invalid")
        os.close(descriptor)
        descriptor = None
        os.fsync(parent)
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("refinement_evidence_registration_invalid") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)
    relative = _refinement_manifest_path(session_id, candidate_id, run_id)
    return ArtifactRef(relative, hashlib.sha256(encoded).hexdigest(), len(encoded)), encoded


def _after_refinement_result_intent_publication() -> None:
    """Interruption seam after exact result-registration intent is authoritative."""


def _after_refinement_evidence_manifest_publication() -> None:
    """Interruption seam after immutable objects and refinement manifest exist."""


def _after_refinement_result_state_publication() -> None:
    """Interruption seam after the final result/evidence state is durable."""


def _registration_receipt_payload(
    *,
    registration_intent: ArtifactRef,
    intent_payload: Mapping[str, object],
    manifest_reference: ArtifactRef,
    manifest_filesystem_identity: Mapping[str, int],
    object_filesystem_identities: list[dict[str, object]],
    receipt_filesystem_identity: Mapping[str, int],
    manifest_payload: Mapping[str, object],
    result_payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "registration_id": intent_payload["registration_id"],
        "project_id": intent_payload["project_id"],
        "session_id": intent_payload["session_id"],
        "candidate_id": intent_payload["candidate_id"],
        "run_id": intent_payload["run_id"],
        "producer": intent_payload["producer"],
        "producer_role": intent_payload["producer_role"],
        "created_at": intent_payload["created_at"],
        "registration_intent": _artifact_payload(registration_intent),
        "receipt_filesystem_identity": dict(receipt_filesystem_identity),
        "execution_contract": intent_payload["execution_contract"],
        "result": intent_payload["result"],
        "manifest": _artifact_payload(manifest_reference),
        "manifest_filesystem_identity": dict(manifest_filesystem_identity),
        "objects": list(manifest_payload["objects"]),
        "object_filesystem_identities": object_filesystem_identities,
        "runtime": result_payload["runtime"],
        "completed": True,
    }


def _find_candidate_run(
    project: ResearchProject, session_id: str, candidate_id: str
) -> tuple[str, dict[str, str]]:
    inventory = _run_inventory(project, session_id)
    matches: list[tuple[str, dict[str, str]]] = []
    for run_id, records in inventory.items():
        contract_path = records.get("contract")
        if contract_path is None:
            continue
        contract, _bytes, _snapshot = _read_run_payload(
            project, contract_path, error_code="refinement_run_contract_invalid"
        )
        if contract.get("candidate_id") == candidate_id:
            matches.append((run_id, records))
    if len(matches) != 1 or matches[0][0] != sorted(inventory)[-1]:
        raise ValueError("refinement_result_reservation_invalid")
    return matches[0]


def _validated_result_registration_context(
    project: ResearchProject,
    *,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    run_id: str,
    contract_path: str,
    contract: Mapping[str, object],
    contract_bytes: bytes,
    registration_intent_path: str,
) -> tuple[
    dict[str, object],
    ArtifactRef,
    dict[str, object],
    ArtifactRef,
    tuple[EvidenceSource, ...],
    float,
]:
    result_path = _run_result_path(candidate.candidate_id)
    result, result_bytes, result_snapshot, elapsed = _validate_refinement_result_payload(
        project,
        candidate,
        package,
        run_id=run_id,
        contract_path=contract_path,
        contract=contract,
        contract_bytes=contract_bytes,
        result_path=result_path,
    )
    result_reference = ArtifactRef(
        result_path, hashlib.sha256(result_bytes).hexdigest(), len(result_bytes)
    )
    sources = _evidence_sources(
        contract,
        contract_path=contract_path,
        contract_bytes=contract_bytes,
        result_path=result_path,
        result_bytes=result_bytes,
    )
    registration_intent, registration_intent_bytes, registration_intent_snapshot = (
        _read_run_payload(
            project,
            registration_intent_path,
            error_code="refinement_evidence_registration_invalid",
        )
    )
    registration_intent_reference = ArtifactRef(
        registration_intent_path,
        hashlib.sha256(registration_intent_bytes).hexdigest(),
        len(registration_intent_bytes),
    )
    state_reference = project.state.artifacts.get(registration_intent_path)
    if state_reference not in {None, registration_intent_reference}:
        raise ValueError("refinement_evidence_registration_invalid")
    try:
        intent_identity = _require_filesystem_identity(
            registration_intent.get("intent_filesystem_identity"),
            receipt=True,
            error="refinement_evidence_registration_invalid",
        )
        registration_id = str(registration_intent["registration_id"])
        created_at = str(registration_intent["created_at"])
        manifest_created_at = str(registration_intent["manifest_created_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("refinement_evidence_registration_invalid") from error
    if intent_identity != _receipt_filesystem_identity_from_snapshot(
        registration_intent_snapshot
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    contract_reference = ArtifactRef(
        contract_path, hashlib.sha256(contract_bytes).hexdigest(), len(contract_bytes)
    )
    manifest_path = _refinement_manifest_path(
        str(contract["session_id"]), candidate.candidate_id, run_id
    )
    expected_intent = _registration_intent_payload(
        contract=contract,
        registration_id=registration_id,
        created_at=created_at,
        manifest_created_at=manifest_created_at,
        contract_reference=contract_reference,
        result_reference=result_reference,
        result_filesystem_identity=_filesystem_identity(result_snapshot),
        sources=sources,
        manifest_path=manifest_path,
        filesystem_identity=intent_identity,
    )
    if registration_intent != expected_intent:
        raise ValueError("refinement_evidence_registration_invalid")
    return (
        registration_intent,
        registration_intent_reference,
        result,
        result_reference,
        sources,
        elapsed,
    )


def _validated_refinement_manifest(
    project: ResearchProject,
    *,
    registration_intent: Mapping[str, object],
    result: Mapping[str, object],
) -> tuple[dict[str, object], ArtifactRef, object, list[dict[str, object]]]:
    manifest_path = registration_intent.get("manifest_path")
    if not isinstance(manifest_path, str):
        raise ValueError("refinement_evidence_registration_invalid")
    manifest, manifest_bytes, manifest_snapshot = _read_run_payload(
        project,
        manifest_path,
        error_code="refinement_evidence_registration_invalid",
    )
    expected_manifest = _manifest_payload(registration_intent, result)
    if manifest != expected_manifest:
        raise ValueError("refinement_evidence_registration_invalid")
    manifest_reference = ArtifactRef(
        manifest_path,
        hashlib.sha256(manifest_bytes).hexdigest(),
        len(manifest_bytes),
    )
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise ValueError("refinement_evidence_registration_invalid")
    identities: list[dict[str, object]] = []
    for item in objects:
        if not isinstance(item, Mapping):
            raise ValueError("refinement_evidence_registration_invalid")
        object_path = item.get("object_path")
        sha256 = item.get("sha256")
        size = item.get("size")
        if (
            not isinstance(object_path, str)
            or not isinstance(sha256, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError("refinement_evidence_registration_invalid")
        object_reference = ArtifactRef(object_path, sha256, size)
        object_snapshot = _secure_snapshot(
            project.root,
            object_path,
            expected=object_reference,
            maximum_bytes=size,
            error_code="refinement_evidence_registration_invalid",
        )[0]
        identities.append({"path": object_path, **_filesystem_identity(object_snapshot)})
    return manifest, manifest_reference, manifest_snapshot, identities


def _validate_pending_result_registration(
    project: ResearchProject,
    *,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    run_id: str,
    contract_path: str,
    contract: Mapping[str, object],
    contract_bytes: bytes,
    registration_intent_path: str,
) -> None:
    registration_intent, _intent_ref, result, _result_ref, _sources, _elapsed = (
        _validated_result_registration_context(
            project,
            candidate=candidate,
            package=package,
            run_id=run_id,
            contract_path=contract_path,
            contract=contract,
            contract_bytes=contract_bytes,
            registration_intent_path=registration_intent_path,
        )
    )
    _authoritative_run_wall_seconds(
        contract, _reservation_time(registration_intent.get("created_at"))
    )
    manifest_path = str(registration_intent["manifest_path"])
    if os.path.lexists(project.root / manifest_path):
        _validated_refinement_manifest(
            project, registration_intent=registration_intent, result=result
        )
    if (
        project.state.artifacts.get(_run_result_path(candidate.candidate_id)) is not None
        or project.state.artifacts.get(manifest_path) is not None
        or project.state.artifacts.get(
            _run_registration_path(str(contract["session_id"]), run_id)
        )
        is not None
    ):
        raise ValueError("refinement_evidence_registration_invalid")


def _validate_completed_result_registration(
    project: ResearchProject,
    *,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    run_id: str,
    contract_path: str,
    contract: Mapping[str, object],
    contract_bytes: bytes,
    registration_intent_path: str,
    registration_path: str,
) -> float:
    (
        registration_intent,
        registration_intent_reference,
        result,
        result_reference,
        _sources,
        _reported_elapsed,
    ) = _validated_result_registration_context(
        project,
        candidate=candidate,
        package=package,
        run_id=run_id,
        contract_path=contract_path,
        contract=contract,
        contract_bytes=contract_bytes,
        registration_intent_path=registration_intent_path,
    )
    if project.state.artifacts.get(registration_intent_path) != (
        registration_intent_reference
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    manifest, manifest_reference, manifest_snapshot, object_identities = (
        _validated_refinement_manifest(
            project, registration_intent=registration_intent, result=result
        )
    )
    receipt, receipt_bytes, receipt_snapshot = _read_run_payload(
        project,
        registration_path,
        error_code="refinement_evidence_registration_invalid",
    )
    expected_receipt = _registration_receipt_payload(
        registration_intent=registration_intent_reference,
        intent_payload=registration_intent,
        manifest_reference=manifest_reference,
        manifest_filesystem_identity=_filesystem_identity(manifest_snapshot),
        object_filesystem_identities=object_identities,
        receipt_filesystem_identity=_receipt_filesystem_identity_from_snapshot(
            receipt_snapshot
        ),
        manifest_payload=manifest,
        result_payload=result,
    )
    if receipt != expected_receipt:
        raise ValueError("refinement_evidence_registration_invalid")
    receipt_reference = ArtifactRef(
        registration_path, hashlib.sha256(receipt_bytes).hexdigest(), len(receipt_bytes)
    )
    manifest_path = str(registration_intent["manifest_path"])
    state_publication = (
        project.state.artifacts.get(_run_result_path(candidate.candidate_id)),
        project.state.artifacts.get(manifest_path),
        project.state.artifacts.get(registration_path),
    )
    complete_state = (result_reference, manifest_reference, receipt_reference)
    recoverable_state = (None, None, None)
    if state_publication != complete_state and not (
        state_publication == recoverable_state
        and project.state.next_action == "register_refinement_result"
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    return _authoritative_run_wall_seconds(
        contract, _reservation_time(registration_intent.get("created_at"))
    )


def _reconstruct_refinement_run_counters(
    project: ResearchProject, candidates: tuple[CandidateStatus, ...]
) -> tuple[int, float]:
    session_payload = _current_session_payload(project)
    session_id = str(session_payload["session_id"])
    inventory = _run_inventory(project, session_id)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ValueError("refinement_run_reservation_invalid")
    wall_seconds = 0.0
    prior_run_complete = True
    for run_number, (run_id, records) in enumerate(inventory.items(), start=1):
        if not prior_run_complete:
            raise ValueError("refinement_run_reservation_invalid")
        intent_path = records["intent"]
        intent, intent_bytes, intent_snapshot = _read_run_payload(
            project, intent_path, error_code="refinement_run_reservation_invalid"
        )
        candidate_id = intent.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise ValueError("refinement_run_reservation_invalid")
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            raise ValueError("refinement_run_reservation_invalid")
        _revalidate_registered_self_test_semantics(project, candidate)
        context = _hold_candidate_context(project, candidate)
        package = validate_experiment_package_contract_at(
            project,
            package_root=_candidate_root(project, candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        bound_environment = _inspect_bound_environment(package)
        contract_path = _run_contract_path(session_id, run_id)
        authority = _run_authority_payload(
            project,
            candidate,
            context,
            package,
            bound_environment,
            session_payload=session_payload,
            run_id=run_id,
            contract_path=contract_path,
            runs_reserved_before=run_number - 1,
            wall_seconds_used_before=wall_seconds,
            reservation_time=_reservation_time(intent.get("created_at")),
        )
        result_path = _run_result_path(candidate_id)
        _validate_run_intent(
            intent,
            intent_snapshot,
            authority=authority,
            contract_path=contract_path,
            result_path=result_path,
        )
        intent_reference = ArtifactRef(
            intent_path, hashlib.sha256(intent_bytes).hexdigest(), len(intent_bytes)
        )
        state_intent = project.state.artifacts.get(intent_path)
        if state_intent not in {None, intent_reference}:
            raise ValueError("refinement_run_reservation_invalid")
        contract_path = records.get("contract")
        if contract_path is None:
            if records.keys() != {"intent"}:
                raise ValueError("refinement_run_reservation_invalid")
            prior_run_complete = False
            continue
        if state_intent != intent_reference:
            raise ValueError("refinement_run_reservation_invalid")
        contract, contract_bytes, contract_snapshot = _read_run_payload(
            project, contract_path, error_code="refinement_run_contract_invalid"
        )
        expected_contract = _run_contract_payload(
            intent,
            intent_reference,
            _receipt_filesystem_identity_from_snapshot(contract_snapshot),
        )
        if contract != expected_contract:
            raise ValueError("refinement_run_contract_invalid")
        contract_reference = ArtifactRef(
            contract_path,
            hashlib.sha256(contract_bytes).hexdigest(),
            len(contract_bytes),
        )
        state_contract = project.state.artifacts.get(contract_path)
        if state_contract not in {None, contract_reference}:
            raise ValueError("refinement_run_contract_invalid")
        registration_path = records.get("registration")
        registration_intent_path = records.get("registration.intent")
        if registration_path is None:
            if records.keys() not in (
                {"intent", "contract"},
                {"intent", "contract", "registration.intent"},
            ):
                raise ValueError("refinement_evidence_registration_invalid")
            if state_contract not in {None, contract_reference}:
                raise ValueError("refinement_run_contract_invalid")
            if registration_intent_path is not None:
                if state_contract != contract_reference:
                    raise ValueError("refinement_run_contract_invalid")
                _validate_pending_result_registration(
                    project,
                    candidate=candidate,
                    package=package,
                    run_id=run_id,
                    contract_path=contract_path,
                    contract=contract,
                    contract_bytes=contract_bytes,
                    registration_intent_path=registration_intent_path,
                )
            prior_run_complete = False
            continue
        if registration_intent_path is None or state_contract != contract_reference:
            raise ValueError("refinement_evidence_registration_invalid")
        elapsed = _validate_completed_result_registration(
            project,
            candidate=candidate,
            package=package,
            run_id=run_id,
            contract_path=contract_path,
            contract=contract,
            contract_bytes=contract_bytes,
            registration_intent_path=registration_intent_path,
            registration_path=registration_path,
        )
        wall_seconds += elapsed
        maximum_wall_seconds = session_payload.get("envelope", {}).get(
            "maximum_wall_seconds"
        )
        if (
            isinstance(maximum_wall_seconds, bool)
            or not isinstance(maximum_wall_seconds, int)
            or wall_seconds > maximum_wall_seconds
        ):
            raise ValueError("refinement_run_wall_time_exhausted")
    return len(inventory), wall_seconds


@project_mutation
def register_refinement_result(
    project: ResearchProject, candidate_id: str, result_path: str | Path
) -> RefinementRunStatus:
    """Validate one owned run result and publish immutable refinement evidence."""
    current = ResearchProject.open(project.root)
    expected_result_path = _run_result_path(candidate_id)
    supplied = Path(result_path)
    if supplied.is_absolute() or supplied.as_posix() != expected_result_path:
        raise ValueError("refinement_result_path_invalid")
    if current.state.next_action not in {
        "register_refinement_result",
        "register_refinement_assessment",
    }:
        raise ValueError("refinement_result_unavailable")
    session_payload = _current_session_payload(current)
    session_id = str(session_payload["session_id"])
    run_id, records = _find_candidate_run(current, session_id, candidate_id)
    session_status = _load_prepared_refinement_session(current)
    candidate_statuses = _registered_candidate_statuses(
        current,
        session=session_status,
        baseline=_baseline(current),
        unregistered_additional_paths=(
            {candidate_id: (expected_result_path,)}
            if expected_result_path not in current.state.artifacts
            else None
        ),
    )
    _reconstruct_refinement_run_counters(current, candidate_statuses)
    candidate = _revalidate_refinement_candidate(
        current,
        candidate_id,
        unregistered_result_path=(
            None
            if expected_result_path in current.state.artifacts
            else expected_result_path
        ),
    )
    _revalidate_registered_self_test_semantics(current, candidate)
    context = _hold_candidate_context(current, candidate)
    package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    bound_environment = _inspect_bound_environment(package)
    inventory = _run_inventory(current, session_id)
    prior_inventory = {
        prior_run_id: prior_records
        for prior_run_id, prior_records in inventory.items()
        if prior_run_id < run_id
    }
    intent_path = records.get("intent")
    contract_path = records.get("contract")
    if intent_path is None or contract_path is None:
        raise ValueError("refinement_result_reservation_invalid")
    reservation_time = _reservation_time(
        _read_run_payload(
            current,
            intent_path,
            error_code="refinement_run_reservation_invalid",
        )[0].get("created_at")
    )
    authority = _run_authority_payload(
        current,
        candidate,
        context,
        package,
        bound_environment,
        session_payload=session_payload,
        run_id=run_id,
        contract_path=contract_path,
        runs_reserved_before=int(run_id.split("-")[1]) - 1,
        wall_seconds_used_before=_completed_run_wall_seconds(current, prior_inventory),
        reservation_time=reservation_time,
    )
    intent, intent_bytes, intent_snapshot = _read_run_payload(
        current, intent_path, error_code="refinement_run_reservation_invalid"
    )
    _validate_run_intent(
        intent,
        intent_snapshot,
        authority=authority,
        contract_path=contract_path,
        result_path=expected_result_path,
    )
    intent_reference = ArtifactRef(
        intent_path, hashlib.sha256(intent_bytes).hexdigest(), len(intent_bytes)
    )
    contract, contract_bytes, contract_snapshot = _read_run_payload(
        current, contract_path, error_code="refinement_run_contract_invalid"
    )
    if contract != _run_contract_payload(
        intent,
        intent_reference,
        _receipt_filesystem_identity_from_snapshot(contract_snapshot),
    ):
        raise ValueError("refinement_run_contract_invalid")
    contract_reference = ArtifactRef(
        contract_path, hashlib.sha256(contract_bytes).hexdigest(), len(contract_bytes)
    )
    if (
        current.state.artifacts.get(intent_path) != intent_reference
        or current.state.artifacts.get(contract_path) != contract_reference
    ):
        raise ValueError("refinement_result_reservation_invalid")
    registration_observed_at: datetime | None = None
    registration_intent_path = _registration_intent_path(session_id, run_id)
    registered_intent_authority = _read_intent_authority(
        current,
        registration_intent_path,
        error_code="refinement_evidence_registration_invalid",
    )
    if (
        registration_intent_path not in current.state.artifacts
        and registered_intent_authority is None
    ):
        registration_observed_at = _utc_now()
        _authoritative_run_wall_seconds(contract, registration_observed_at)
    (
        result,
        result_bytes,
        result_snapshot,
        _reported_elapsed,
    ) = _validate_refinement_result_payload(
        current,
        candidate,
        package,
        run_id=run_id,
        contract_path=contract_path,
        contract=contract,
        contract_bytes=contract_bytes,
        result_path=expected_result_path,
    )
    result_reference = ArtifactRef(
        expected_result_path,
        hashlib.sha256(result_bytes).hexdigest(),
        len(result_bytes),
    )
    existing_result = current.state.artifacts.get(expected_result_path)
    if existing_result not in {None, result_reference}:
        raise ValueError("refinement_result_changed")
    sources = _evidence_sources(
        contract,
        contract_path=contract_path,
        contract_bytes=contract_bytes,
        result_path=expected_result_path,
        result_bytes=result_bytes,
    )
    manifest_path = _refinement_manifest_path(session_id, candidate_id, run_id)
    registration_intent_path = _registration_intent_path(session_id, run_id)
    registration_path = _run_registration_path(session_id, run_id)
    registration_intent_ref = current.state.artifacts.get(registration_intent_path)
    adopt_registration_intent = False
    created_registration_intent = False
    if registration_intent_ref is None:
        adopt_registration_intent = True
        registration_id = uuid4().hex
        if registered_intent_authority is None:
            # Acceptance time is sampled by the controller, never supplied by
            # the result or an uncommitted previous staging attempt.
            registration_observed_at = _utc_now()
            _authoritative_run_wall_seconds(contract, registration_observed_at)

        def build_registration(identity):
            if registration_observed_at is None:
                raise ValueError("refinement_evidence_registration_invalid")
            registration_created_at = registration_observed_at.isoformat()
            return _registration_intent_payload(
                contract=contract,
                registration_id=registration_id,
                created_at=registration_created_at,
                manifest_created_at=registration_created_at,
                contract_reference=contract_reference,
                result_reference=result_reference,
                result_filesystem_identity=_filesystem_identity(result_snapshot),
                sources=sources,
                manifest_path=manifest_path,
                filesystem_identity=identity,
            )

        parent = _open_run_parent(current, session_id)
        try:
            registration_intent, registration_intent_bytes = _publish_authorized_intent(
                current,
                intent_path=registration_intent_path,
                parent_descriptor=parent,
                payload_builder=build_registration,
                error_code="refinement_evidence_registration_invalid",
                before_accept=lambda: _authoritative_run_wall_seconds(
                    contract, _utc_now()
                ),
            )
        finally:
            os.close(parent)
        current = ResearchProject.open_readonly(current.root)
        registration_intent_snapshot = _read_run_payload(
            current,
            registration_intent_path,
            error_code="refinement_evidence_registration_invalid",
        )[2]
        created_registration_intent = True
        registration_intent_ref = ArtifactRef(
            registration_intent_path,
            hashlib.sha256(registration_intent_bytes).hexdigest(),
            len(registration_intent_bytes),
        )
    else:
        (
            registration_intent,
            registration_intent_bytes,
            registration_intent_snapshot,
        ) = _read_run_payload(
            current,
            registration_intent_path,
            error_code="refinement_evidence_registration_invalid",
        )
        if registration_intent_snapshot.reference != registration_intent_ref:
            raise ValueError("refinement_evidence_registration_invalid")
    (
        registration_intent,
        registration_intent_bytes,
        registration_intent_snapshot,
    ) = _read_run_payload(
        current,
        registration_intent_path,
        error_code="refinement_evidence_registration_invalid",
    )
    if registration_intent_snapshot.reference != registration_intent_ref:
        raise ValueError("refinement_evidence_registration_invalid")
    expected_registration = _registration_intent_payload(
        contract=contract,
        registration_id=str(registration_intent["registration_id"]),
        created_at=str(registration_intent["created_at"]),
        manifest_created_at=str(registration_intent["manifest_created_at"]),
        contract_reference=contract_reference,
        result_reference=result_reference,
        result_filesystem_identity=_filesystem_identity(result_snapshot),
        sources=sources,
        manifest_path=manifest_path,
        filesystem_identity=_require_filesystem_identity(
            registration_intent.get("intent_filesystem_identity"),
            receipt=True,
            error="refinement_evidence_registration_invalid",
        ),
    )
    if registration_intent != expected_registration:
        raise ValueError("refinement_evidence_registration_invalid")
    _authoritative_run_wall_seconds(
        contract, _reservation_time(registration_intent.get("created_at"))
    )
    if _require_filesystem_identity(
        registration_intent.get("intent_filesystem_identity"),
        receipt=True,
        error="refinement_evidence_registration_invalid",
    ) != _receipt_filesystem_identity_from_snapshot(registration_intent_snapshot):
        raise ValueError("refinement_evidence_registration_invalid")
    if adopt_registration_intent:
        current.persist_state(
            replace(
                current.state,
                artifacts={
                    **current.state.artifacts,
                    registration_intent_path: registration_intent_ref,
                },
            )
        )
        current = ResearchProject.open(current.root)
        if created_registration_intent:
            _after_refinement_result_intent_publication()
    store = EvidenceStore(current.root)
    store.preflight(sources)
    evidence_objects = tuple(store.publish(source) for source in sources)
    if any(
        evidence_object.sha256 != source.expected_sha256
        or evidence_object.size != source.expected_size
        for source, evidence_object in zip(sources, evidence_objects, strict=True)
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    manifest_payload = _manifest_payload(registration_intent, result)
    manifest_reference, _manifest_bytes = _write_refinement_manifest(
        current,
        session_id=session_id,
        candidate_id=candidate_id,
        run_id=run_id,
        payload=manifest_payload,
    )
    manifest_snapshot = _secure_snapshot(
        current.root,
        manifest_path,
        expected=manifest_reference,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_evidence_registration_invalid",
    )[0]
    object_filesystem_identities: list[dict[str, object]] = []
    for evidence_object in evidence_objects:
        object_reference = ArtifactRef(
            evidence_object.path, evidence_object.sha256, evidence_object.size
        )
        object_snapshot = _secure_snapshot(
            current.root,
            evidence_object.path,
            expected=object_reference,
            maximum_bytes=evidence_object.size,
            error_code="refinement_evidence_registration_invalid",
        )[0]
        object_filesystem_identities.append(
            {"path": evidence_object.path, **_filesystem_identity(object_snapshot)}
        )
    _after_refinement_evidence_manifest_publication()
    if os.path.lexists(current.root / registration_path):
        persisted_receipt, receipt_bytes, receipt_snapshot = _read_run_payload(
            current,
            registration_path,
            error_code="refinement_evidence_registration_invalid",
        )
        receipt_payload = _registration_receipt_payload(
            registration_intent=registration_intent_ref,
            intent_payload=registration_intent,
            manifest_reference=manifest_reference,
            manifest_filesystem_identity=_filesystem_identity(manifest_snapshot),
            object_filesystem_identities=object_filesystem_identities,
            receipt_filesystem_identity=(
                _receipt_filesystem_identity_from_snapshot(receipt_snapshot)
            ),
            manifest_payload=manifest_payload,
            result_payload=result,
        )
        receipt_bytes_expected = _canonical_json(receipt_payload)
        if (
            persisted_receipt != receipt_payload
            or receipt_bytes != receipt_bytes_expected
        ):
            raise ValueError("refinement_evidence_registration_invalid")
    else:
        try:
            receipt_payload, receipt_bytes = _write_run_record(
                current,
                session_id=session_id,
                leaf_name=f"{run_id}.registration.json",
                payload_builder=lambda identity: _registration_receipt_payload(
                    registration_intent=registration_intent_ref,
                    intent_payload=registration_intent,
                    manifest_reference=manifest_reference,
                    manifest_filesystem_identity=_filesystem_identity(
                        manifest_snapshot
                    ),
                    object_filesystem_identities=object_filesystem_identities,
                    receipt_filesystem_identity=identity,
                    manifest_payload=manifest_payload,
                    result_payload=result,
                ),
                error_code="refinement_evidence_registration_invalid",
            )
        except FileExistsError as error:
            raise ValueError("refinement_evidence_registration_invalid") from error
        receipt_snapshot = _read_run_payload(
            current,
            registration_path,
            error_code="refinement_evidence_registration_invalid",
        )[2]
        if receipt_payload != _registration_receipt_payload(
            registration_intent=registration_intent_ref,
            intent_payload=registration_intent,
            manifest_reference=manifest_reference,
            manifest_filesystem_identity=_filesystem_identity(manifest_snapshot),
            object_filesystem_identities=object_filesystem_identities,
            receipt_filesystem_identity=(
                _receipt_filesystem_identity_from_snapshot(receipt_snapshot)
            ),
            manifest_payload=manifest_payload,
            result_payload=result,
        ):
            raise ValueError("refinement_evidence_registration_invalid")
    receipt_reference = ArtifactRef(
        registration_path, hashlib.sha256(receipt_bytes).hexdigest(), len(receipt_bytes)
    )
    target_state = replace(
        current.state,
        next_action="register_refinement_assessment",
        artifacts={
            **current.state.artifacts,
            expected_result_path: result_reference,
            manifest_path: manifest_reference,
            registration_path: receipt_reference,
        },
    )
    if current.state != target_state:
        current.persist_state(target_state)
        _after_refinement_result_state_publication()
    published = ResearchProject.open_readonly(current.root)
    if (
        published.state != target_state
        or _secure_snapshot(
            published.root,
            expected_result_path,
            expected=result_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_result_changed",
        )[0].reference
        != result_reference
        or _secure_snapshot(
            published.root,
            manifest_path,
            expected=manifest_reference,
            maximum_bytes=_MAX_JSON_BYTES,
            error_code="refinement_evidence_registration_invalid",
        )[0].reference
        != manifest_reference
        or _inspect_bound_environment(package) != bound_environment
    ):
        raise ValueError("refinement_evidence_registration_invalid")
    published_session = _load_prepared_refinement_session(published)
    published_candidates = tuple(
        replace(item, next_action=published.state.next_action)
        for item in _registered_candidate_statuses(
            published,
            session=published_session,
            baseline=_baseline(published),
        )
    )
    runs_used, wall_seconds_used = _reconstruct_refinement_run_counters(
        published, published_candidates
    )
    execution = contract["execution"]
    assert isinstance(execution, Mapping)
    return RefinementRunStatus(
        candidate_id=candidate_id,
        run_id=run_id,
        argv=tuple(str(item) for item in execution["argv"]),
        cwd=str(execution["cwd"]),
        environment_fingerprint=str(execution["environment_fingerprint"]),
        intent_path=intent_path,
        contract_path=contract_path,
        contract_sha256=contract_snapshot.reference.sha256,
        result_path=expected_result_path,
        evidence_manifest_path=manifest_path,
        runs_used=runs_used,
        wall_seconds_used=wall_seconds_used,
        next_action="register_refinement_assessment",
    )
