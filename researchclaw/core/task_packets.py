"""Versioned, backend-neutral packets for executing research stages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .approval import load_approval_record, verify_current_approval
from .contracts import LITERATURE_APPROVAL_STAGE, SUPPORTED_STAGE_IDS, get_contract
from .models import StageStatus
from .paths import resolve_project_artifact
from .profiles import load_profile
from .project import ResearchProject

_HASH_CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TaskPacket:
    schema_version: int
    project_id: str
    project_root: str
    write_policy: str
    stage_id: int
    name: str
    objective: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    allowed_tool_classes: tuple[str, ...]
    requires_approval: bool
    profile_context: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_root": self.project_root,
            "write_policy": self.write_policy,
            "stage_id": self.stage_id,
            "name": self.name,
            "objective": self.objective,
            "required_inputs": list(self.required_inputs),
            "required_outputs": list(self.required_outputs),
            "acceptance_criteria": list(self.acceptance_criteria),
            "allowed_tool_classes": list(self.allowed_tool_classes),
            "requires_approval": self.requires_approval,
            "profile_context": {key: list(value) for key, value in self.profile_context.items()},
        }


def build_task_packet(project: ResearchProject) -> TaskPacket:
    """Build a task packet without observable workflow side effects."""
    state = project.state
    if state.status is StageStatus.COMPLETED or state.current_stage > 23:
        raise ValueError("project is complete")
    if state.status is StageStatus.BLOCKED:
        raise ValueError("validation retry limit reached; user review is required")
    if state.status is StageStatus.AWAITING_APPROVAL:
        raise ValueError("project is awaiting approval")
    if state.current_stage not in SUPPORTED_STAGE_IDS:
        raise ValueError(f"task packets are not defined for stage: {state.current_stage}")
    if state.current_stage == 6:
        record = load_approval_record(project.root, LITERATURE_APPROVAL_STAGE)
        if (
            record is None
            or record.decision != "approve"
            or not verify_current_approval(project.root, record)
        ):
            raise ValueError("stage 6 requires the approved stage-5 shortlist")
    contract = get_contract(state.current_stage)
    missing: list[str] = []
    for relative_path in contract.required_inputs:
        artifact = state.artifacts.get(relative_path)
        if artifact is None or artifact.path != relative_path:
            missing.append(relative_path)
            continue
        artifact_path = resolve_project_artifact(project.root, relative_path)
        if not artifact_path.is_file():
            missing.append(relative_path)
            continue
        stat = artifact_path.stat()
        if stat.st_size != artifact.size or _sha256(artifact_path) != artifact.sha256:
            raise ValueError(f"required input artifact changed since validation: {relative_path}")
    if missing:
        raise ValueError(f"required input artifacts are missing: {', '.join(missing)}")
    profile = load_profile(state.profile)
    return TaskPacket(
        schema_version=1,
        project_id=state.project_id,
        project_root=str(project.root.resolve()),
        write_policy="declared_outputs_only",
        stage_id=contract.id,
        name=contract.name,
        objective=contract.objective,
        required_inputs=contract.required_inputs,
        required_outputs=contract.required_outputs,
        acceptance_criteria=contract.acceptance_criteria,
        allowed_tool_classes=contract.allowed_tool_classes,
        requires_approval=contract.requires_approval,
        profile_context={
            "preferred_sources": profile.preferred_sources,
            "quality_checks": profile.quality_checks,
            "metric_guidance": profile.metric_guidance,
        },
    )


def prepare_task_packet(project: ResearchProject) -> TaskPacket:
    """Build a packet and record the explicit prepare action."""
    current_project = ResearchProject.open(project.root)
    packet = build_task_packet(current_project)
    for relative_path in packet.required_outputs:
        resolve_project_artifact(current_project.root, relative_path)
    from .events import EvaluationEvent, event_log_for

    event_log_for(current_project.root).append(
        EvaluationEvent.create(
            "task_packet_prepared",
            packet.project_id,
            {
                "stage_id": packet.stage_id,
                "name": packet.name,
                "requires_approval": packet.requires_approval,
            },
        )
    )
    return packet
