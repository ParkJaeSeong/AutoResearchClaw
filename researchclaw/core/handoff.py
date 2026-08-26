"""Reconstruct a safe next step from a project's durable files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .approval import ApprovalRecord, verify_current_approval
from .contracts import get_contract
from .models import ProjectState, StageStatus
from .project import ResearchProject

_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class HandoffSummary:
    project_id: str
    topic: str
    current_stage: int
    stage_name: str
    status: str
    completed_stages: tuple[int, ...]
    available_artifacts: tuple[str, ...]
    approval_required: bool
    next_action: str
    next_command: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "topic": self.topic,
            "current_stage": self.current_stage,
            "stage_name": self.stage_name,
            "status": self.status,
            "completed_stages": list(self.completed_stages),
            "available_artifacts": list(self.available_artifacts),
            "approval_required": self.approval_required,
            "next_action": self.next_action,
            "next_command": self.next_command,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _artifacts_match(root: Path, state: ProjectState) -> bool:
    for relative_path, artifact in state.artifacts.items():
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts or artifact.path != relative_path:
            return False
        artifact_path = root / path
        try:
            if not artifact_path.is_file() or _sha256(artifact_path) != artifact.sha256:
                return False
        except OSError:
            return False
    return True


def _load_approval(root: Path, stage_id: int) -> ApprovalRecord | None:
    path = root / "approvals" / f"stage-{stage_id:02d}.json"
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return None
        return ApprovalRecord(
            schema_version=int(data["schema_version"]),
            project_id=str(data["project_id"]),
            stage_id=int(data["stage_id"]),
            decision=str(data["decision"]),
            artifact_hashes={str(key): str(value) for key, value in data["artifact_hashes"].items()},
            decided_at=str(data["decided_at"]),
            note=str(data["note"]),
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _completed_approvals_match(project: ResearchProject) -> bool:
    for stage_id in project.state.completed_stages:
        try:
            contract = get_contract(stage_id)
        except ValueError:
            return False
        if not contract.requires_approval:
            continue
        record = _load_approval(project.root, stage_id)
        if record is None or record.decision != "approve":
            return False
        if not verify_current_approval(project.root, record):
            return False
    return True


def build_handoff(project: ResearchProject) -> HandoffSummary:
    """Build a handoff using only durable state, artifacts, and approval records."""
    current_project = ResearchProject.open(project.root)
    state = current_project.state
    contract = get_contract(state.current_stage)
    artifacts_are_valid = _artifacts_match(current_project.root, state)
    approvals_are_valid = _completed_approvals_match(current_project)
    status = state.status
    if not artifacts_are_valid or not approvals_are_valid:
        status = StageStatus.NEEDS_REVISION

    if status is StageStatus.NEEDS_REVISION:
        next_action = "validate_stage"
        next_command = "researchclaw stage validate"
    elif status is StageStatus.AWAITING_APPROVAL:
        next_action = "approve"
        next_command = "researchclaw approve"
    else:
        next_action = "prepare_stage"
        next_command = "researchclaw stage prepare"

    available_artifacts = tuple(
        sorted(
            relative_path
            for relative_path in state.artifacts
            if not Path(relative_path).is_absolute()
            and ".." not in Path(relative_path).parts
            and (current_project.root / relative_path).is_file()
        )
    )
    return HandoffSummary(
        project_id=state.project_id,
        topic=state.topic,
        current_stage=state.current_stage,
        stage_name=contract.name,
        status=status.value,
        completed_stages=state.completed_stages,
        available_artifacts=available_artifacts,
        approval_required=contract.requires_approval,
        next_action=next_action,
        next_command=next_command,
    )
