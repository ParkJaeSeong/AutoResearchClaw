"""Hash-bound approvals for human-gated research stages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import get_contract
from .models import ProjectState, StageStatus
from .paths import resolve_project_artifact
from .persistence import atomic_write_json
from .project import ResearchProject

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


def approve_current_gate(project: ResearchProject, decision: str, note: str) -> ApprovalRecord:
    """Persist an approval decision after confirming validated artifacts are unchanged."""
    if decision not in _ALLOWED_DECISIONS:
        raise ValueError("decision must be either 'approve' or 'reject'")

    current_project = ResearchProject.open(project.root)
    state = current_project.state
    if state.status is not StageStatus.AWAITING_APPROVAL:
        raise ValueError("project is not awaiting approval")

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
            next_action="prepare_stage",
            execution_policy=state.execution_policy,
            artifacts=state.artifacts,
            retry_counts=state.retry_counts,
            last_error=state.last_error,
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
