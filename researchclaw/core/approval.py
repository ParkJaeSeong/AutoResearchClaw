"""Hash-bound approvals for human-gated research stages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import SUPPORTED_STAGE_MAX, get_contract
from .models import ProjectState, StageStatus
from .paths import resolve_project_artifact
from .persistence import atomic_write_json
from .project import ResearchProject
from .transactions import project_mutation

_HASH_CHUNK_SIZE = 1024 * 1024
_SCHEMA_VERSION = 1
_ALLOWED_DECISIONS = frozenset({"approve", "reject"})
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ApprovalRecord:
    schema_version: int
    project_id: str
    stage_id: int
    decision: str
    artifact_hashes: dict[str, str]
    decided_at: str
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "stage_id": self.stage_id,
            "decision": self.decision,
            "artifact_hashes": self.artifact_hashes,
            "decided_at": self.decided_at,
            "note": self.note,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_artifact_hashes(root: Path, state: ProjectState, stage_id: int) -> dict[str, str]:
    contract = get_contract(stage_id)
    hashes: dict[str, str] = {}
    for relative_path in contract.required_outputs:
        artifact = state.artifacts.get(relative_path)
        if artifact is None or artifact.path != relative_path:
            raise ValueError(f"persisted artifact hash is missing for {relative_path}")
        path = resolve_project_artifact(root, relative_path)
        if not path.is_file() or _sha256(path) != artifact.sha256:
            raise ValueError(f"artifact has changed since validation: {relative_path}")
        hashes[relative_path] = artifact.sha256
    return hashes


def _approval_path(root: Path, stage_id: int) -> Path:
    return root / "approvals" / f"stage-{stage_id:02d}.json"


def _save_record(path: Path, record: ApprovalRecord) -> None:
    atomic_write_json(path, record.to_dict(), prefix=f"{path.stem}-")


def load_approval_record(root: Path, stage_id: int) -> ApprovalRecord | None:
    """Load one approval record, returning ``None`` for unsafe or malformed data."""
    path = _approval_path(Path(root), stage_id)
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return None
        artifact_hashes = data["artifact_hashes"]
        if (
            not isinstance(data["schema_version"], int)
            or isinstance(data["schema_version"], bool)
            or not isinstance(data["project_id"], str)
            or not isinstance(data["stage_id"], int)
            or isinstance(data["stage_id"], bool)
            or not isinstance(data["decision"], str)
            or not isinstance(artifact_hashes, Mapping)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in artifact_hashes.items())
            or not isinstance(data["decided_at"], str)
            or not isinstance(data["note"], str)
        ):
            return None
        for relative_path, digest in artifact_hashes.items():
            resolve_project_artifact(Path(root), relative_path)
            if _HASH_PATTERN.fullmatch(digest) is None:
                return None
        record = ApprovalRecord(
            schema_version=data["schema_version"],
            project_id=data["project_id"],
            stage_id=data["stage_id"],
            decision=data["decision"],
            artifact_hashes=dict(artifact_hashes),
            decided_at=data["decided_at"],
            note=data["note"],
        )
        return record if record.stage_id == stage_id else None
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


@project_mutation
def approve_current_gate(project: ResearchProject, decision: str, note: str) -> ApprovalRecord:
    """Persist an approval decision after confirming validated artifacts are unchanged."""
    if decision not in _ALLOWED_DECISIONS:
        raise ValueError("decision must be either 'approve' or 'reject'")

    current_project = ResearchProject.open(project.root)
    if current_project.state.current_stage == 12:
        from .handoff import normalize_durable_project

        current_project = normalize_durable_project(current_project)
    state = current_project.state
    if state.status is not StageStatus.AWAITING_APPROVAL:
        raise ValueError("project is not awaiting approval")

    if state.current_stage == 12:
        return _approve_stage_twelve(current_project, decision, note)

    contract = get_contract(state.current_stage)
    if not contract.requires_approval:
        raise ValueError(f"stage {state.current_stage} does not require approval")

    artifact_hashes = _stage_artifact_hashes(current_project.root, state, contract.id)
    record = ApprovalRecord(
        schema_version=_SCHEMA_VERSION,
        project_id=state.project_id,
        stage_id=contract.id,
        decision=decision,
        artifact_hashes=artifact_hashes,
        decided_at=datetime.now(timezone.utc).isoformat(),
        note=note,
    )
    _save_record(_approval_path(current_project.root, contract.id), record)

    if decision == "approve":
        completed_stages = state.completed_stages
        if contract.id not in completed_stages:
            completed_stages = (*completed_stages, contract.id)
        updated_state = ProjectState(
            schema_version=state.schema_version,
            project_id=state.project_id,
            topic=state.topic,
            profile=state.profile,
            current_stage=contract.id + 1,
            status=StageStatus.READY,
            completed_stages=completed_stages,
            next_action=(
                "report_validation_design_milestone_only"
                if contract.id == SUPPORTED_STAGE_MAX
                else "prepare_stage"
            ),
            execution_policy=state.execution_policy,
            artifacts=state.artifacts,
            retry_counts=state.retry_counts,
            last_error=state.last_error,
            stage_10_snapshot=state.stage_10_snapshot,
        )
    else:
        updated_state = ProjectState(
            schema_version=state.schema_version,
            project_id=state.project_id,
            topic=state.topic,
            profile=state.profile,
            current_stage=state.current_stage,
            status=StageStatus.NEEDS_REVISION,
            completed_stages=state.completed_stages,
            next_action="prepare_stage",
            execution_policy=state.execution_policy,
            artifacts=state.artifacts,
            retry_counts=state.retry_counts,
            last_error=state.last_error,
            stage_10_snapshot=state.stage_10_snapshot,
        )
    current_project.persist_state(updated_state)
    from .events import EvaluationEvent, event_log_for

    event_log_for(current_project.root).append(
        EvaluationEvent.create(
            "approval_decision",
            state.project_id,
            {"stage_id": record.stage_id, "decision": record.decision},
        )
    )
    return record


def _approve_stage_twelve(
    project: ResearchProject,
    decision: str,
    note: str,
) -> ApprovalRecord:
    """Record the execution decision without running or importing the package."""
    from .execution_gate import (
        _recheck_execution_readiness,
        stage_twelve_artifact_hashes,
    )

    state = project.state
    self_test_artifact = None
    if decision == "approve":
        from .experiment_package_contract import _current_registered_self_test

        self_test_artifact = _current_registered_self_test(project)
    prior_record = load_approval_record(project.root, 12)
    current_rejection = (
        prior_record is not None
        and prior_record.decision == "reject"
        and approval_matches_state(project.root, state, prior_record)
    )
    registration_recovery = (
        state.next_action == "approve_experiment_execution"
        and isinstance(state.last_error, dict)
        and state.last_error.get("retry_state")
        == "stage_twelve_registration_recovery"
    )
    if state.next_action != "approve_experiment_execution" and not (
        state.next_action == "report_missing_execution_inputs"
        and current_rejection
    ):
        raise ValueError("execution prerequisites are not ready for approval")
    status = _recheck_execution_readiness(
        project,
        allow_rejected_decision=current_rejection,
        allow_preexisting_result=registration_recovery,
    )
    if not status.approval_eligible or status.readiness != "ready_for_execution":
        raise ValueError("execution prerequisites are not ready for approval")

    refreshed_project = ResearchProject.open(project.root)
    artifact_hashes = stage_twelve_artifact_hashes(refreshed_project)
    if self_test_artifact is not None:
        artifact_hashes[self_test_artifact.path] = self_test_artifact.sha256
    record = ApprovalRecord(
        schema_version=_SCHEMA_VERSION,
        project_id=refreshed_project.state.project_id,
        stage_id=12,
        decision=decision,
        artifact_hashes=artifact_hashes,
        decided_at=datetime.now(timezone.utc).isoformat(),
        note=note,
    )
    _save_record(_approval_path(refreshed_project.root, 12), record)
    if decision == "approve":
        updated_state = ProjectState(
            schema_version=refreshed_project.state.schema_version,
            project_id=refreshed_project.state.project_id,
            topic=refreshed_project.state.topic,
            profile=refreshed_project.state.profile,
            current_stage=12,
            status=StageStatus.READY,
            completed_stages=refreshed_project.state.completed_stages,
            next_action=(
                "register_research_result"
                if registration_recovery
                else "report_resource_plan_milestone_only"
            ),
            execution_policy=refreshed_project.state.execution_policy,
            artifacts=refreshed_project.state.artifacts,
            retry_counts=refreshed_project.state.retry_counts,
            last_error=(
                state.last_error
                if registration_recovery
                else refreshed_project.state.last_error
            ),
            stage_10_snapshot=refreshed_project.state.stage_10_snapshot,
        )
    else:
        updated_state = ProjectState(
            schema_version=refreshed_project.state.schema_version,
            project_id=refreshed_project.state.project_id,
            topic=refreshed_project.state.topic,
            profile=refreshed_project.state.profile,
            current_stage=12,
            status=StageStatus.AWAITING_APPROVAL,
            completed_stages=refreshed_project.state.completed_stages,
            next_action="report_missing_execution_inputs",
            execution_policy=refreshed_project.state.execution_policy,
            artifacts=refreshed_project.state.artifacts,
            retry_counts=refreshed_project.state.retry_counts,
            last_error=(
                state.last_error
                if registration_recovery
                else refreshed_project.state.last_error
            ),
            stage_10_snapshot=refreshed_project.state.stage_10_snapshot,
        )
    refreshed_project.persist_state(updated_state)
    from .events import EvaluationEvent, event_log_for

    event_log_for(refreshed_project.root).append(
        EvaluationEvent.create(
            "approval_decision",
            refreshed_project.state.project_id,
            {"stage_id": 12, "decision": decision},
        )
    )
    return record


def approval_matches_state(root: Path, state: ProjectState, record: ApprovalRecord) -> bool:
    """Return whether a record still matches an already-loaded persisted state."""
    try:
        root = Path(root)
        if (
            record.schema_version != _SCHEMA_VERSION
            or record.decision not in _ALLOWED_DECISIONS
            or record.project_id != state.project_id
        ):
            return False
        if record.stage_id == 12:
            from .execution_gate import _stage_twelve_artifact_hashes

            expected_hashes = _stage_twelve_artifact_hashes(root, state)
            if record.decision == "approve":
                from .experiment_package_contract import _current_registered_self_test

                self_test = _current_registered_self_test(
                    ResearchProject(root=root, state=state)
                )
                expected_hashes[self_test.path] = self_test.sha256
            return record.artifact_hashes == expected_hashes
        contract = get_contract(record.stage_id)
        if not contract.requires_approval or set(record.artifact_hashes) != set(contract.required_outputs):
            return False
        for relative_path in contract.required_outputs:
            artifact = state.artifacts.get(relative_path)
            if artifact is None or artifact.path != relative_path:
                return False
            path = resolve_project_artifact(root, relative_path)
            if not path.is_file() or artifact.sha256 != record.artifact_hashes[relative_path]:
                return False
            if _sha256(path) != record.artifact_hashes[relative_path]:
                return False
        return True
    except (OSError, ValueError):
        return False


def verify_current_approval(project: Path, record: ApprovalRecord) -> bool:
    """Return whether a record still matches the persisted artifacts on disk."""
    try:
        root = Path(project)
        return approval_matches_state(root, ResearchProject.open(root).state, record)
    except (OSError, ValueError):
        return False
