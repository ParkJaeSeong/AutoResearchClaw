"""Versioned, backend-neutral packets for executing research stages."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import get_contract
from .profiles import load_profile
from .project import ResearchProject

_STAGE_ARTIFACTS: dict[int, tuple[tuple[str, ...], tuple[str, ...]]] = {
    1: ((), ("scope/goal.md", "scope/hardware_profile.json")),
    2: (("scope/goal.md", "scope/hardware_profile.json"), ("scope/problem_tree.md",)),
    3: (("scope/problem_tree.md",), ("literature/search_plan.yaml",)),
    4: (("literature/search_plan.yaml",), ("literature/candidates.jsonl",)),
    5: (("literature/candidates.jsonl",), ("literature/shortlist.jsonl",)),
}


@dataclass(frozen=True)
class TaskPacket:
    schema_version: int
    project_id: str
    stage_id: int
    name: str
    objective: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    allowed_tool_classes: tuple[str, ...]
    requires_approval: bool
    profile_context: dict[str, tuple[str, ...]]
    artifact_root: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "stage_id": self.stage_id,
            "name": self.name,
            "objective": self.objective,
            "required_inputs": list(self.required_inputs),
            "required_outputs": list(self.required_outputs),
            "acceptance_criteria": list(self.acceptance_criteria),
            "allowed_tool_classes": list(self.allowed_tool_classes),
            "requires_approval": self.requires_approval,
            "profile_context": {key: list(value) for key, value in self.profile_context.items()},
            "artifact_root": self.artifact_root,
        }


def prepare_task_packet(project: ResearchProject) -> TaskPacket:
    """Build a stage packet without changing persisted project state."""
    state = project.state
    if state.status.value == "completed" or state.current_stage > 23:
        raise ValueError("project is complete")
    contract = get_contract(state.current_stage)
    try:
        required_inputs, required_outputs = _STAGE_ARTIFACTS[state.current_stage]
    except KeyError as exc:
        raise ValueError(f"task packets are not defined for stage: {state.current_stage}") from exc
    missing = [
        path
        for path in required_inputs
        if not any(key == path or artifact.path == path for key, artifact in state.artifacts.items())
    ]
    if missing:
        raise ValueError(f"required input artifacts are missing: {', '.join(missing)}")
    profile = load_profile(state.profile)
    return TaskPacket(
        schema_version=1,
        project_id=state.project_id,
        stage_id=contract.id,
        name=contract.name,
        objective=contract.objective,
        required_inputs=required_inputs,
        required_outputs=required_outputs,
        acceptance_criteria=contract.acceptance_criteria,
        allowed_tool_classes=contract.allowed_tool_classes,
        requires_approval=contract.requires_approval,
        profile_context={
            "preferred_sources": profile.preferred_sources,
            "quality_checks": profile.quality_checks,
            "metric_guidance": profile.metric_guidance,
        },
        artifact_root="artifacts",
    )
