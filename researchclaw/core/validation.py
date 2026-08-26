"""Deterministic validation and advancement for the first five research stages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .contracts import StageContract, get_contract
from .models import ArtifactRef, StageStatus
from .project import ResearchProject
from .task_packets import TaskPacket, prepare_task_packet

_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class ValidationReport:
    stage_id: int
    valid: bool
    issues: tuple[ValidationIssue, ...]
    artifact_refs: dict[str, ArtifactRef]

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "artifact_refs": {
                path: {"path": ref.path, "sha256": ref.sha256, "size": ref.size}
                for path, ref in self.artifact_refs.items()
            },
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path, issues: list[ValidationIssue], relative_path: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        issues.append(ValidationIssue("invalid_format", relative_path, "artifact must be UTF-8 text"))
        return None


def _invalid(issues: list[ValidationIssue], path: str, message: str) -> None:
    issues.append(ValidationIssue("invalid_format", path, message))


def _validate_stage_one(contents: dict[str, str], issues: list[ValidationIssue]) -> None:
    goal_path = "scope/goal.md"
    goal_lines = (line.strip() for line in contents[goal_path].splitlines())
    if not any(line and not line.startswith("#") and re.search(r"[.!?]", line) for line in goal_lines):
        _invalid(issues, goal_path, "goal.md must contain a non-heading sentence")

    hardware_path = "scope/hardware_profile.json"
    try:
        hardware = json.loads(contents[hardware_path])
    except json.JSONDecodeError:
        _invalid(issues, hardware_path, "hardware_profile.json must be valid JSON")
    else:
        if not isinstance(hardware, dict):
            _invalid(issues, hardware_path, "hardware_profile.json must contain a JSON object")


def _validate_stage_two(contents: dict[str, str], issues: list[ValidationIssue]) -> None:
    path = "scope/problem_tree.md"
    questions = re.findall(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+).+\?\s*$", contents[path])
    if len(questions) < 3:
        _invalid(issues, path, "problem_tree.md must contain at least three numbered or bullet questions")


def _validate_stage_three(contents: dict[str, str], issues: list[ValidationIssue]) -> None:
    path = "literature/search_plan.yaml"
    try:
        plan = yaml.safe_load(contents[path])
    except yaml.YAMLError:
        _invalid(issues, path, "search_plan.yaml must be valid YAML")
        return
    if not isinstance(plan, dict) or not isinstance(plan.get("queries"), list) or not plan["queries"]:
        _invalid(issues, path, "search_plan.yaml must be a mapping with a non-empty queries list")


def _validate_jsonl(
    contents: dict[str, str],
    issues: list[ValidationIssue],
    path: str,
    required_fields: tuple[str, ...],
    *,
    identifier_required: bool = False,
    decisions_required: bool = False,
) -> None:
    for line_number, line in enumerate(contents[path].splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record: Any = json.loads(line)
        except json.JSONDecodeError:
            _invalid(issues, path, f"line {line_number} must be valid JSON")
            return
        if not isinstance(record, dict):
            _invalid(issues, path, f"line {line_number} must be a JSON object")
            return
        if any(not record.get(field) for field in required_fields):
            _invalid(issues, path, f"line {line_number} is missing required fields")
            return
        if identifier_required and not any(record.get(field) for field in ("doi", "arxiv_id", "url")):
            _invalid(issues, path, f"line {line_number} requires doi, arxiv_id, or url")
            return
        if decisions_required and record["decision"] not in {"include", "exclude"}:
            _invalid(issues, path, f"line {line_number} has an invalid decision")
            return


def _validate_format(stage_id: int, contents: dict[str, str], issues: list[ValidationIssue]) -> None:
    if stage_id == 1:
        _validate_stage_one(contents, issues)
    elif stage_id == 2:
        _validate_stage_two(contents, issues)
    elif stage_id == 3:
        _validate_stage_three(contents, issues)
    elif stage_id == 4:
        _validate_jsonl(
            contents,
            issues,
            "literature/candidates.jsonl",
            ("title",),
            identifier_required=True,
        )
    elif stage_id == 5:
        _validate_jsonl(
            contents,
            issues,
            "literature/shortlist.jsonl",
            ("title", "decision", "reason"),
            decisions_required=True,
        )


def _current_packet_and_contract(project: ResearchProject) -> tuple[TaskPacket, StageContract]:
    packet = prepare_task_packet(project)
    contract = get_contract(packet.stage_id)
    if contract.id != packet.stage_id:
        raise ValueError(f"task packet stage does not match its contract: {packet.stage_id}")
    return packet, contract


def validate_current_stage(project: ResearchProject) -> ValidationReport:
    """Validate the current task packet's outputs and persist its resulting state."""
    packet, _contract = _current_packet_and_contract(project)
    issues: list[ValidationIssue] = []
    artifact_refs: dict[str, ArtifactRef] = {}
    contents: dict[str, str] = {}

    for relative_path in packet.required_outputs:
        path = project.root / relative_path
        if not path.is_file():
            issues.append(ValidationIssue("missing_artifact", relative_path, "required artifact is missing"))
            continue
        if path.stat().st_size == 0:
            issues.append(ValidationIssue("empty_artifact", relative_path, "required artifact is empty"))
            continue
        artifact_refs[relative_path] = ArtifactRef(
            path=relative_path,
            sha256=_sha256(path),
            size=path.stat().st_size,
        )
        text = _read_text(path, issues, relative_path)
        if text is None:
            continue
        if not text.strip():
            issues.append(ValidationIssue("empty_artifact", relative_path, "required artifact is empty"))
            continue
        contents[relative_path] = text

    if not issues and len(contents) == len(packet.required_outputs):
        _validate_format(packet.stage_id, contents, issues)

    report = ValidationReport(
        stage_id=packet.stage_id,
        valid=not issues,
        issues=tuple(issues),
        artifact_refs=artifact_refs,
    )
    advance_validated_stage(project, report)
    return report


def advance_validated_stage(project: ResearchProject, report: ValidationReport) -> ResearchProject:
    """Atomically persist the outcome of a validation report for the current stage."""
    state = project.state
    if report.stage_id != state.current_stage:
        raise ValueError("validation report does not match the current stage")

    if not report.valid:
        return project.persist_state(replace(state, status=StageStatus.NEEDS_REVISION))

    contract = get_contract(report.stage_id)
    artifacts = {**state.artifacts, **report.artifact_refs}
    if contract.requires_approval:
        updated_state = replace(
            state,
            status=StageStatus.AWAITING_APPROVAL,
            next_action="await_approval",
            artifacts=artifacts,
        )
    else:
        completed_stages = state.completed_stages
        if report.stage_id not in completed_stages:
            completed_stages = (*completed_stages, report.stage_id)
        updated_state = replace(
            state,
            current_stage=report.stage_id + 1,
            completed_stages=completed_stages,
            status=StageStatus.READY,
            next_action="prepare_stage",
            artifacts=artifacts,
        )
    return project.persist_state(updated_state)
