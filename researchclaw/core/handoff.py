"""Reconstruct a safe next step from a project's durable files."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from .approval import ApprovalRecord, verify_current_approval
from .contracts import FOUNDATION_STAGE_IDS, FOUNDATION_STAGE_MAX, get_contract, stage_for_output
from .models import ProjectState, StageStatus
from .paths import resolve_project_artifact, validate_relative_path
from .project import ResearchProject

_HASH_CHUNK_SIZE = 1024 * 1024
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class HandoffSummary:
    project_id: str
    project_root: str
    write_policy: str
    topic: str
    current_stage: int
    stage_name: str
    status: str
    completed_stages: tuple[int, ...]
    available_artifacts: tuple[str, ...]
    approval_required: bool
    milestone_complete: bool
    next_action: str
    next_command: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "project_root": self.project_root,
            "write_policy": self.write_policy,
            "topic": self.topic,
            "current_stage": self.current_stage,
            "stage_name": self.stage_name,
            "status": self.status,
            "completed_stages": list(self.completed_stages),
            "available_artifacts": list(self.available_artifacts),
            "approval_required": self.approval_required,
            "milestone_complete": self.milestone_complete,
            "next_action": self.next_action,
            "next_command": self.next_command,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _first_invalid_artifact_stage(root: Path, state: ProjectState) -> int | None:
    ordered_artifacts = sorted(
        state.artifacts.items(),
        key=lambda item: stage_for_output(item[0]) or FOUNDATION_STAGE_MAX,
    )
    for relative_path, artifact in ordered_artifacts:
        producing_stage = stage_for_output(relative_path) or min(
            state.current_stage,
            FOUNDATION_STAGE_MAX,
        )
        try:
            if artifact.path != relative_path:
                return producing_stage
            artifact_path = resolve_project_artifact(root, relative_path)
            if not artifact_path.is_file():
                return producing_stage
            stat = artifact_path.stat()
            if stat.st_size != artifact.size or _sha256(artifact_path) != artifact.sha256:
                return producing_stage
        except (OSError, ValueError):
            return producing_stage
    return None


def _load_approval(root: Path, stage_id: int) -> ApprovalRecord | None:
    path = root / "approvals" / f"stage-{stage_id:02d}.json"
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
            validate_relative_path(relative_path, kind="artifact")
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


def _first_invalid_completed_approval_stage(project: ResearchProject) -> int | None:
    for stage_id in project.state.completed_stages:
        try:
            contract = get_contract(stage_id)
        except ValueError:
            return stage_id
        if not contract.requires_approval:
            continue
        record = _load_approval(project.root, stage_id)
        if record is None or record.decision != "approve":
            return stage_id
        if not verify_current_approval(project.root, record):
            return stage_id
    return None


def _rewind_for_revalidation(
    project: ResearchProject,
    stage_id: int,
    *,
    approval_invalidated: bool,
) -> ResearchProject:
    state = project.state
    code = "approval_invalidated" if approval_invalidated else "artifact_invalidated"
    message = (
        "approved artifact changed; validate stage and request a new approval"
        if approval_invalidated
        else "persisted artifact changed; validate the producing stage again"
    )
    relevant_hashes = {
        path: artifact.sha256
        for path, artifact in state.artifacts.items()
        if stage_for_output(path) == stage_id
    }
    issue_path = get_contract(stage_id).required_outputs[0]
    last_error: dict[str, object] = {
        "error_class": StageStatus.NEEDS_REVISION.value,
        "stage_id": stage_id,
        "attempt_number": state.retry_counts.get(str(stage_id), 0) + 1,
        "issues": [{"code": code, "path": issue_path, "message": message}],
        "artifact_hashes": relevant_hashes,
        "recommended_action": "revalidate_stage_and_request_new_approval"
        if approval_invalidated
        else "revalidate_changed_artifacts",
        "retry_state": code,
    }
    return project.persist_state(
        replace(
            state,
            current_stage=stage_id,
            status=StageStatus.NEEDS_REVISION,
            completed_stages=tuple(stage for stage in state.completed_stages if stage < stage_id),
            next_action="validate_stage",
            last_error=last_error,
        )
    )


def _available_artifacts(root: Path, state: ProjectState) -> tuple[str, ...]:
    available: list[str] = []
    for relative_path in sorted(state.artifacts):
        try:
            artifact_path = resolve_project_artifact(root, relative_path)
            if artifact_path.is_file():
                available.append(relative_path)
        except (OSError, ValueError):
            continue
    return tuple(available)


def _command(root: Path, *arguments: str) -> str:
    return shlex.join(("researchclaw-codex", *arguments, str(root.resolve()), "--json"))


def build_handoff(project: ResearchProject) -> HandoffSummary:
    """Build a handoff using only durable state, artifacts, and approval records."""
    current_project = ResearchProject.open(project.root)
    state = current_project.state
    invalid_artifact_stage = _first_invalid_artifact_stage(current_project.root, state)
    invalid_approval_stage = _first_invalid_completed_approval_stage(current_project)
    invalid_stages = [
        stage_id
        for stage_id in (invalid_artifact_stage, invalid_approval_stage)
        if stage_id is not None
    ]
    if invalid_stages:
        rewind_stage = min(invalid_stages)
        current_project = _rewind_for_revalidation(
            current_project,
            rewind_stage,
            approval_invalidated=invalid_approval_stage == rewind_stage,
        )
        state = current_project.state

    milestone_complete = (
        state.current_stage > FOUNDATION_STAGE_MAX
        and all(stage_id in state.completed_stages for stage_id in FOUNDATION_STAGE_IDS)
    )
    if state.current_stage > 23:
        stage_name = "project_complete"
        approval_required = False
    else:
        contract = get_contract(state.current_stage)
        stage_name = contract.name
        approval_required = contract.requires_approval

    status = state.status
    if milestone_complete:
        next_action = "report_foundation_milestone_only"
        next_command = _command(current_project.root, "evaluate")
    elif status is StageStatus.NEEDS_REVISION:
        next_action = "validate_stage"
        next_command = _command(current_project.root, "stage", "validate")
    elif status is StageStatus.AWAITING_APPROVAL:
        next_action = "approve"
        next_command = shlex.join(
            (
                "researchclaw-codex",
                "approve",
                str(current_project.root.resolve()),
                "--decision",
                "<approve|reject>",
                "--json",
            )
        )
    elif status is StageStatus.BLOCKED:
        next_action = "review_blocked_stage"
        next_command = _command(current_project.root, "status")
    else:
        next_action = "prepare_stage"
        next_command = _command(current_project.root, "stage", "prepare")

    return HandoffSummary(
        project_id=state.project_id,
        project_root=str(current_project.root.resolve()),
        write_policy="no_undeclared_outputs" if milestone_complete else "declared_outputs_only",
        topic=state.topic,
        current_stage=state.current_stage,
        stage_name=stage_name,
        status=status.value,
        completed_stages=state.completed_stages,
        available_artifacts=_available_artifacts(current_project.root, state),
        approval_required=approval_required,
        milestone_complete=milestone_complete,
        next_action=next_action,
        next_command=next_command,
    )
