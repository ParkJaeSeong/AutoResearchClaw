"""Versioned, backend-neutral packets for executing research stages."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

from .approval import load_approval_record, verify_current_approval
from .contracts import LITERATURE_APPROVAL_STAGE, SUPPORTED_STAGE_IDS, get_contract
from .filesystem_baseline import snapshot_project
from .models import StageStatus, StageTenSnapshot
from .paths import resolve_project_artifact
from .profiles import load_profile
from .project import ResearchProject
from .resource_planning import observe_local_hardware
from .transactions import project_mutation

_HASH_CHUNK_SIZE = 1024 * 1024
_SUSPICIOUS_LEGACY_STAGE_TEN_PATH_FAMILIES = (
    "analysis",
    "result",
    "output",
    "download",
    "notebook",
    "ipynb",
    "package_manifest",
    "package-manifest",
)


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
    if state.current_stage == 13:
        raise ValueError(
            "Stage 13 uses researchclaw-codex refinement prepare-session PROJECT "
            "--envelope PROJECT_RELATIVE_PATH --json, not stage prepare; "
            "review the refinement envelope before explicitly preparing a session."
        )
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
    if state.current_stage in {10, 11}:
        record = load_approval_record(project.root, 9)
        if (
            record is None
            or record.decision != "approve"
            or not verify_current_approval(project.root, record)
        ):
            raise ValueError(
                f"stage {state.current_stage} requires the approved stage-9 validation design"
            )
    if state.current_stage == 10:
        design = json.loads(
            resolve_project_artifact(project.root, "experiment/design.json").read_text(
                encoding="utf-8"
            )
        )
        validation_type = design.get("validation_type")
        if validation_type != "computational":
            raise ValueError(f"stage 10 does not support {validation_type}")
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
    profile_context = {
        "preferred_sources": profile.preferred_sources,
        "quality_checks": profile.quality_checks,
        "metric_guidance": profile.metric_guidance,
    }
    if state.current_stage == 11:
        observation = observe_local_hardware(project.root)
        profile_context.update(
            {
                "hardware_observation": (
                    json.dumps(observation.to_dict(), sort_keys=True),
                ),
                "deferred_command": (
                    "python experiment/code/main.py --config experiment/code/config.json",
                ),
                "result_path": ("experiment/results.json",),
            }
        )
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
        profile_context=profile_context,
    )


def _legacy_stage_ten_baseline_blockers(
    root: Path, required_outputs: tuple[str, ...]
) -> tuple[str, ...]:
    blockers: set[str] = set()
    outputs = {
        unicodedata.normalize("NFKC", output).casefold() for output in required_outputs
    }
    for entry in snapshot_project(root):
        relative = entry.path
        normalized = unicodedata.normalize("NFKC", relative).casefold()
        if normalized in outputs or normalized == "experiment/code" or normalized.startswith(
            "experiment/code/"
        ):
            blockers.add(relative)
            continue
        if any(
            family in normalized
            for family in _SUSPICIOUS_LEGACY_STAGE_TEN_PATH_FAMILIES
        ):
            blockers.add(relative)
    return tuple(sorted(blockers))


@project_mutation
def prepare_task_packet(
    project: ResearchProject, *, establish_legacy_baseline: bool = False
) -> TaskPacket:
    """Build a packet and record the explicit prepare action."""
    current_project = ResearchProject.open(project.root)
    if establish_legacy_baseline and (
        current_project.state.current_stage != 10
        or current_project.state.stage_10_snapshot.status != "legacy_missing"
    ):
        raise ValueError(
            "--establish-legacy-baseline is only valid for legacy-missing Stage 10 state"
        )
    packet = build_task_packet(current_project)
    for relative_path in packet.required_outputs:
        resolve_project_artifact(current_project.root, relative_path)
    if packet.stage_id == 10:
        snapshot = current_project.state.stage_10_snapshot
        if snapshot.status == "legacy_missing":
            if not establish_legacy_baseline:
                raise ValueError(
                    "legacy Stage 10 state is missing its immutable filesystem snapshot"
                )
            blockers = _legacy_stage_ten_baseline_blockers(
                current_project.root, packet.required_outputs
            )
            if blockers:
                raise ValueError(
                    "refusing legacy Stage 10 baseline because suspicious artifacts exist: "
                    + ", ".join(blockers)
                )
            baseline = snapshot_project(current_project.root)
            current_project = current_project.persist_state(
                replace(
                    current_project.state,
                    stage_10_snapshot=StageTenSnapshot("captured", baseline),
                )
            )
            from .events import EvaluationEvent, event_log_for

            event_log_for(current_project.root).append(
                EvaluationEvent.create(
                    "legacy_stage_10_baseline_established",
                    packet.project_id,
                    {"stage_id": 10, "entry_count": len(baseline)},
                )
            )
            snapshot = current_project.state.stage_10_snapshot
        if snapshot.status == "not_prepared":
            baseline = snapshot_project(current_project.root)
            current_project = current_project.persist_state(
                replace(
                    current_project.state,
                    stage_10_snapshot=StageTenSnapshot("captured", baseline),
                )
            )
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
