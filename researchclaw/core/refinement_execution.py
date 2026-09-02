"""Development-only validation and registration for Stage-13 candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from .execution_environment import ExecutionEnvironment, inspect_execution_environment
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
    _reject_duplicate_keys,
    _read_bounded_json,
    _revalidate_refinement_candidate,
    _same_published_baseline_snapshot,
    _secure_snapshot,
    revalidate_refinement_candidate,
)
from .transactions import project_mutation


REFINEMENT_SELF_TEST_REGISTRATION_ROOT = ".researchclaw/refinement-self-tests"
_REPORT_LOCAL_PATH = "package_metadata/self_test_report.json"
_CONTRACT_LOCAL_PATH = "package_metadata/package_contract.json"
_MANIFEST_LOCAL_PATH = "package_metadata/package_manifest.json"
_MAX_JSON_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPORT_KEYS = {
    "schema_version",
    "project_id",
    "session_id",
    "candidate_id",
    "producer",
    "producer_role",
    "created_at",
    "preparation",
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
    "created_at",
    "report_created_at",
    "preparation",
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
            "context_id": self.context_id,
            "context_sha256": self.context_sha256,
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
class _ValidatedPreparation:
    reference: ArtifactRef
    snapshot: object
    payload: Mapping[str, object]
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
    if before.reference != after.reference or before.stat_identity != after.stat_identity:
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
        project.root.resolve(strict=True)
        / "refinement"
        / "candidates"
        / candidate_id
    )


def _parse_held_json(payload: bytes, *, error: str) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exception:
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
    if candidate_manifest is None or session_reference is None or evidence_packet is None:
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


def _report_context_payload(
    *,
    project: ResearchProject,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    created_at: str,
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
        "created_at": created_at,
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
        "fixture": _artifact_payload(
            _candidate_reference(candidate, fixture_path)
        ),
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
    metrics = self_test.get("expected_metrics") if isinstance(self_test, Mapping) else None
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("refinement_self_test_preparation_invalid")
    return list(metrics)


def _preparation_payload(
    *,
    project: ResearchProject,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[
        ExecutionEnvironment, tuple[tuple[object, ...], ...]
    ],
    created_at: str,
    filesystem_identity: Mapping[str, int],
) -> dict[str, object]:
    base = {
        "schema_version": 1,
        **_report_context_payload(
            project=project,
            candidate=candidate,
            context=context,
            package=package,
            created_at=created_at,
        ),
        "expected_metrics": _expected_self_test_metrics(project, candidate),
        "self_test_argv": list(package.self_test_argv),
        "environment_fingerprint": bound_environment[0].fingerprint,
        "execution_environment": _environment_payload(bound_environment[0]),
        "launcher_identity": [list(item) for item in bound_environment[1]],
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
    return {
        key: payload[key]
        for key in (
            "project_id",
            "session_id",
            "candidate_id",
            "producer",
            "producer_role",
            "created_at",
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
    } | {"preparation": _artifact_payload(preparation.reference)}


def _preparation_path(session_id: str, candidate_id: str) -> str:
    return (
        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
        f"{candidate_id}.preparation.json"
    )


@project_mutation
def prepare_refinement_self_test(
    project: ResearchProject, candidate_id: str
) -> SelfTestPreparationStatus:
    """Return a verified candidate command without executing or reserving a run."""
    current = ResearchProject.open(project.root)
    starting_state = current.state
    candidate = revalidate_refinement_candidate(current, candidate_id)
    root = _candidate_root(current, candidate_id)
    report_path = (
        f"refinement/candidates/{candidate_id}/package_metadata/self_test_report.json"
    )
    if os.path.lexists(current.root / report_path):
        raise ValueError("refinement_self_test_report_exists")
    session_payload, _session_bytes = _read_bounded_json(current.root / SESSION_PATH)
    session_id = session_payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("refinement_self_test_preparation_invalid")
    preparation_parent = _open_registration_parent(current, session_id)
    os.close(preparation_parent)
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    context_before = _hold_candidate_context(current, candidate)
    if context_before.session_id != session_id:
        raise ValueError("refinement_self_test_preparation_invalid")
    state_before = _state_file_snapshot(current)[0]
    package = validate_experiment_package_contract_at(
        current,
        package_root=root,
        contract_path="package_metadata/package_contract.json",
    )
    bound_environment = _inspect_bound_environment(package)
    preparation_path = _preparation_path(context_before.session_id, candidate_id)
    registered_preparation = starting_state.artifacts.get(preparation_path)
    preparation_exists = os.path.lexists(current.root / preparation_path)
    if registered_preparation is not None and not preparation_exists:
        raise ValueError("refinement_self_test_preparation_invalid")
    if preparation_exists:
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=registered_preparation,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=bound_environment,
        )
    else:
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            payload, payload_bytes = _write_anchored_record(
                current,
                session_id=context_before.session_id,
                leaf_name=f"{candidate_id}.preparation.json",
                payload_builder=lambda identity: _preparation_payload(
                    project=current,
                    candidate=candidate,
                    context=context_before,
                    package=package,
                    bound_environment=bound_environment,
                    created_at=created_at,
                    filesystem_identity=identity,
                ),
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
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=bound_environment,
        )
        if preparation.payload != payload:
            raise ValueError("refinement_self_test_preparation_invalid")
    target_state = replace(
        starting_state,
        artifacts={
            **starting_state.artifacts,
            preparation_path: preparation.reference,
        },
    )
    if registered_preparation is not None:
        if registered_preparation != preparation.reference or target_state != starting_state:
            raise ValueError("refinement_self_test_preparation_invalid")
    else:
        current_state_snapshot = _state_file_snapshot(current)[0]
        if (
            current_state_snapshot.reference != state_before.reference
            or current_state_snapshot.stat_identity != state_before.stat_identity
            or ResearchProject.open_readonly(current.root).state != starting_state
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
        authoritative_preparation = _read_and_validate_preparation(
            project=published,
            path=preparation_path,
            expected_reference=preparation.reference,
            candidate=authoritative_candidate,
            context=authoritative_context,
            package=authoritative_package,
            bound_environment=bound_environment,
        )
        authoritative_baseline = _baseline_registration_snapshot(
            published, baseline
        )
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
            checked_candidate = _revalidate_refinement_candidate(published, candidate_id)
            checked_context = _hold_candidate_context(published, checked_candidate)
            checked_package = validate_experiment_package_contract_at(
                published,
                package_root=root,
                contract_path=_CONTRACT_LOCAL_PATH,
            )
            checked_preparation = _read_and_validate_preparation(
                project=published,
                path=preparation_path,
                expected_reference=preparation.reference,
                candidate=checked_candidate,
                context=checked_context,
                package=checked_package,
                bound_environment=bound_environment,
            )
            if (
                checked_candidate != candidate
                or checked_context != context_before
                or checked_package != package
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
            if rollback.state != starting_state:
                rollback.persist_state(starting_state)
        raise
    environment, launcher_identity = bound_environment
    context_argument = _canonical_json(
        _external_report_context(preparation)
    ).decode("utf-8")
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


def _candidate_reference(
    candidate: CandidateStatus, local_path: str
) -> ArtifactRef:
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


def _report_artifact_list(
    value: object, expected: tuple[ArtifactRef, ...]
) -> None:
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
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float("-inf") < float(value) < float("inf")
    )


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
    bound_environment: tuple[
        ExecutionEnvironment, tuple[tuple[object, ...], ...]
    ],
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
    _require_closed(
        report, _REPORT_KEYS, error="refinement_self_test_report_invalid"
    )
    if (
        report.get("schema_version") != 1
        or isinstance(report.get("schema_version"), bool)
        or report.get("passed") is not True
        or report.get("development_only") is not True
    ):
        raise ValueError("refinement_self_test_report_invalid")
    try:
        created_at = _created_at(report.get("created_at"))
    except ValueError as error:
        raise ValueError("refinement_self_test_report_invalid") from error
    expected_report_context = _external_report_context(preparation)
    if created_at != preparation.created_at or any(
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
    keys = (
        _RECEIPT_FILESYSTEM_IDENTITY_KEYS if receipt else _FILESYSTEM_IDENTITY_KEYS
    )
    payload = _require_closed(value, keys, error=error)
    if any(isinstance(payload.get(key), bool) or not isinstance(payload.get(key), int) for key in keys):
        raise ValueError(error)
    return {key: int(payload[key]) for key in keys}


def _open_registration_parent(
    project: ResearchProject, session_id: str
) -> int:
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
                raise ValueError(
                    "refinement_self_test_registration_recovery_invalid"
                )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ValueError) as error:
        if "descriptor" in locals():
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise ValueError("refinement_self_test_registration_recovery_invalid") from error


def _write_anchored_record(
    project: ResearchProject,
    *,
    session_id: str,
    leaf_name: str,
    payload_builder,
    before_leaf_create=None,
    error_code: str,
) -> tuple[dict[str, object], bytes]:
    parent_descriptor = _open_registration_parent(project, session_id)
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
        if (
            _receipt_filesystem_identity(final)
            != _receipt_filesystem_identity(initial)
            or final.st_size != len(encoded)
        ):
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
        leaf_name=f"{candidate_id}.json",
        payload_builder=payload_builder,
        before_leaf_create=_before_anchored_registration_leaf_create,
        error_code="refinement_self_test_registration_recovery_invalid",
    )


def _read_and_validate_preparation(
    *,
    project: ResearchProject,
    path: str,
    expected_reference: ArtifactRef | None,
    candidate: CandidateStatus,
    context: _HeldCandidateContext,
    package: package_contract.ValidatedExperimentPackage,
    bound_environment: tuple[
        ExecutionEnvironment, tuple[tuple[object, ...], ...]
    ],
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
        if (
            payload.get("environment_fingerprint") != bound_environment[0].fingerprint
            or payload.get("execution_environment")
            != _environment_payload(bound_environment[0])
            or payload.get("launcher_identity")
            != [list(item) for item in bound_environment[1]]
        ):
            raise ValueError("refinement_self_test_environment_changed")
        created_at = _created_at(payload.get("created_at"))
        identity = _receipt_filesystem_identity_from_snapshot(snapshot)
        expected = _preparation_payload(
            project=project,
            candidate=candidate,
            context=context,
            package=package,
            bound_environment=bound_environment,
            created_at=created_at,
            filesystem_identity=identity,
        )
    except ValueError as error:
        if str(error) == "refinement_self_test_environment_changed":
            raise
        raise ValueError("refinement_self_test_preparation_invalid") from error
    except OSError as error:
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
    bound_environment: tuple[
        ExecutionEnvironment, tuple[tuple[object, ...], ...]
    ],
) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    role_references = [
        ("candidate_manifest", context.candidate_manifest),
        ("council_decision", context.council_decision),
        ("evidence_packet", context.evidence_packet),
        ("baseline_manifest", context.baseline_manifest),
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
        "created_at": preparation.created_at,
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
    bound_environment: tuple[
        ExecutionEnvironment, tuple[tuple[object, ...], ...]
    ],
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
    if receipt_identity != current_receipt_identity or report_identity != current_report_identity:
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
    if registration_payload != expected or registration_bytes != _canonical_json(expected):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    return expected


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
        report_path = _candidate_report_path(candidate.candidate_id)
        report_reference = current.state.artifacts.get(report_path)
        registration_reference = current.state.artifacts.get(registration_path)
        preparation_reference = current.state.artifacts.get(preparation_path)
        if (
            report_reference is None
            or registration_reference is None
            or preparation_reference is None
        ):
            raise ValueError("refinement_candidate_identity_changed")
        package = validate_experiment_package_contract_at(
            current,
            package_root=_candidate_root(current, candidate.candidate_id),
            contract_path=_CONTRACT_LOCAL_PATH,
        )
        environment_before = _inspect_bound_environment(package)
        preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            candidate=candidate,
            context=context_before,
            package=package,
            bound_environment=environment_before,
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
        if (
            context_after != context_before
            or report_after != validated.report_snapshot
            or receipt_after != registration_snapshot
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
    session_payload, _session_bytes = _read_bounded_json(current.root / SESSION_PATH)
    session_id = session_payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("refinement_integrity_failure")
    registration_path = _registration_path(session_id, candidate_id)
    registered_report = starting_state.artifacts.get(expected_report_path)
    registered_registration = starting_state.artifacts.get(registration_path)
    complete_registration = (
        registered_report is not None
        and registered_registration is not None
        and starting_state.next_action == "prepare_refinement_run"
    )
    if any(
        (
            registered_report is not None,
            registered_registration is not None,
            starting_state.next_action == "prepare_refinement_run",
        )
    ) and not complete_registration:
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    candidate = _revalidate_refinement_candidate(
        current,
        candidate_id,
        unregistered_report_path=(
            None if complete_registration else expected_report_path
        ),
    )
    if not complete_registration and candidate.next_action != "prepare_refinement_self_test":
        raise ValueError("refinement_self_test_registration_unavailable")
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    context_before = _hold_candidate_context(current, candidate)
    if context_before.session_id != session_id:
        raise ValueError("refinement_candidate_binding_invalid")
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
    preparation_reference = starting_state.artifacts.get(preparation_path)
    if preparation_reference is None:
        raise ValueError("refinement_self_test_preparation_invalid")
    preparation = _read_and_validate_preparation(
        project=current,
        path=preparation_path,
        expected_reference=preparation_reference,
        candidate=candidate,
        context=context_before,
        package=package,
        bound_environment=environment_before,
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
    refreshed_preparation = _read_and_validate_preparation(
        project=current,
        path=preparation_path,
        expected_reference=preparation_reference,
        candidate=candidate,
        context=context_before,
        package=package,
        bound_environment=environment_before,
    )
    if (
        refreshed_preparation.reference != preparation.reference
        or refreshed_preparation.payload != preparation.payload
        or not _same_snapshot_with_expected_directory_updates(
            preparation.snapshot,
            refreshed_preparation.snapshot,
            allowed_ctime_paths=frozenset(
                {
                    f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/"
                    f"{session_id}"
                }
            ),
        )
    ):
        raise ValueError("refinement_candidate_identity_changed")
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
        checked_preparation = _read_and_validate_preparation(
            project=current,
            path=preparation_path,
            expected_reference=preparation_reference,
            candidate=checked_candidate,
            context=checked_context,
            package=checked_package,
            bound_environment=environment_before,
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
