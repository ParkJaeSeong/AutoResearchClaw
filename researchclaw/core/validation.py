"""Deterministic validation and advancement for supported research stages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .contracts import SUPPORTED_STAGE_MAX, StageContract, get_contract
from .knowledge_extraction import (
    KnowledgeIssue,
    validate_extraction_shortlist,
    validate_knowledge_extraction,
)
from .models import ArtifactRef, StageStatus
from .synthesis import validate_synthesis
from .paths import resolve_project_artifact
from .project import ResearchProject
from .task_packets import TaskPacket, build_task_packet

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
    attempt_number: int
    recommended_action: str
    retry_state: str
    error_state: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "artifact_refs": {
                path: {"path": ref.path, "sha256": ref.sha256, "size": ref.size}
                for path, ref in self.artifact_refs.items()
            },
            "attempt_number": self.attempt_number,
            "recommended_action": self.recommended_action,
            "retry_state": self.retry_state,
            "error_state": self.error_state,
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


def _validate_stage_one(
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    goal_path, hardware_path = contract.required_outputs
    goal_lines = (line.strip() for line in contents[goal_path].splitlines())
    if not any(line and not line.startswith("#") and re.search(r"[.!?]", line) for line in goal_lines):
        _invalid(issues, goal_path, "goal.md must contain a non-heading sentence")

    try:
        hardware = json.loads(contents[hardware_path])
    except json.JSONDecodeError:
        _invalid(issues, hardware_path, "hardware_profile.json must be valid JSON")
    else:
        if not isinstance(hardware, dict):
            _invalid(issues, hardware_path, "hardware_profile.json must contain a JSON object")


def _validate_stage_two(
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    (path,) = contract.required_outputs
    questions = re.findall(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+).+\?\s*$", contents[path])
    if len(questions) < 3:
        _invalid(issues, path, "problem_tree.md must contain at least three numbered or bullet questions")


def _validate_stage_three(
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    (path,) = contract.required_outputs
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
        if any(
            not isinstance(record.get(field), str) or not record[field].strip()
            for field in required_fields
        ):
            _invalid(issues, path, f"line {line_number} requires non-empty string fields")
            return
        if identifier_required and not any(
            isinstance(record.get(field), str) and record[field].strip()
            for field in ("doi", "arxiv_id", "url")
        ):
            _invalid(issues, path, f"line {line_number} requires doi, arxiv_id, or url")
            return
        if decisions_required and record["decision"] not in {"include", "exclude"}:
            _invalid(issues, path, f"line {line_number} has an invalid decision")
            return


def _validate_format(
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    if contract.id == 1:
        _validate_stage_one(contract, contents, issues)
    elif contract.id == 2:
        _validate_stage_two(contract, contents, issues)
    elif contract.id == 3:
        _validate_stage_three(contract, contents, issues)
    elif contract.id == 4:
        (path,) = contract.required_outputs
        _validate_jsonl(
            contents,
            issues,
            path,
            ("title",),
            identifier_required=True,
        )
    elif contract.id == 5:
        (path,) = contract.required_outputs
        issues.extend(
            ValidationIssue(issue.code, path, issue.message)
            for issue in validate_extraction_shortlist(contents[path])
        )


def _as_validation_issue(
    issue: KnowledgeIssue,
    required_outputs: tuple[str, ...],
) -> ValidationIssue:
    path = issue.path if issue.path in required_outputs else required_outputs[-1]
    return ValidationIssue(code=issue.code, path=path, message=issue.message)


def _validate_stage_six(
    project: ResearchProject,
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    (shortlist_path,) = contract.required_inputs
    try:
        shortlist = resolve_project_artifact(project.root, shortlist_path)
    except ValueError as error:
        issues.append(ValidationIssue("unsafe_artifact_path", shortlist_path, str(error)))
        return
    shortlist_text = _read_text(shortlist, issues, shortlist_path)
    if shortlist_text is None:
        return
    claims_path, manifest_path = contract.required_outputs
    issues.extend(
        _as_validation_issue(issue, contract.required_outputs)
        for issue in validate_knowledge_extraction(
            shortlist_text,
            contents[claims_path],
            contents[manifest_path],
            project.state.project_id,
        )
    )


def _validate_stage_seven(
    project: ResearchProject,
    contract: StageContract,
    contents: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    extractions_path, _manifest_path = contract.required_inputs
    extractions = resolve_project_artifact(project.root, extractions_path)
    extractions_text = _read_text(extractions, issues, extractions_path)
    if extractions_text is None:
        return
    (synthesis_path,) = contract.required_outputs
    issues.extend(
        ValidationIssue(issue.code, synthesis_path, issue.message)
        for issue in validate_synthesis(extractions_text, contents[synthesis_path])
    )


def _current_packet_and_contract(project: ResearchProject) -> tuple[TaskPacket, StageContract]:
    packet = build_task_packet(project)
    contract = get_contract(packet.stage_id)
    if contract.id != packet.stage_id:
        raise ValueError(f"task packet stage does not match its contract: {packet.stage_id}")
    return packet, contract


def validate_current_stage(project: ResearchProject) -> ValidationReport:
    """Validate the current task packet's outputs and persist its resulting state."""
    current_project = ResearchProject.open(project.root)
    packet, contract = _current_packet_and_contract(current_project)
    attempt_number = current_project.state.retry_counts.get(str(packet.stage_id), 0) + 1
    issues: list[ValidationIssue] = []
    artifact_refs: dict[str, ArtifactRef] = {}
    contents: dict[str, str] = {}

    for relative_path in packet.required_outputs:
        allow_empty = packet.stage_id == 6 and relative_path == packet.required_outputs[0]
        try:
            path = resolve_project_artifact(current_project.root, relative_path)
        except ValueError as error:
            issues.append(ValidationIssue("unsafe_artifact_path", relative_path, str(error)))
            continue
        if not path.is_file():
            issues.append(ValidationIssue("missing_artifact", relative_path, "required artifact is missing"))
            continue
        if path.stat().st_size == 0 and not allow_empty:
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
        if not text.strip() and not allow_empty:
            issues.append(ValidationIssue("empty_artifact", relative_path, "required artifact is empty"))
            continue
        contents[relative_path] = text

    if not issues and len(contents) == len(packet.required_outputs):
        _validate_format(contract, contents, issues)
        if not issues and contract.id == 6:
            _validate_stage_six(current_project, contract, contents, issues)
        elif not issues and contract.id == 7:
            _validate_stage_seven(current_project, contract, contents, issues)

    if issues:
        if attempt_number > contract.max_retries:
            retry_state = "retry_limit_reached"
            recommended_action = "review_failures_with_user"
            error_state = StageStatus.BLOCKED.value
        else:
            retry_state = "retry_available"
            recommended_action = "revise_declared_outputs_and_validate_again"
            error_state = StageStatus.NEEDS_REVISION.value
    else:
        retry_state = "succeeded_after_retry" if attempt_number > 1 else "succeeded"
        if contract.requires_approval:
            recommended_action = "request_approval"
        elif contract.id == SUPPORTED_STAGE_MAX:
            recommended_action = "report_synthesis_milestone_only"
        else:
            recommended_action = "prepare_next_stage"
        error_state = None

    report = ValidationReport(
        stage_id=packet.stage_id,
        valid=not issues,
        issues=tuple(issues),
        artifact_refs=artifact_refs,
        attempt_number=attempt_number,
        recommended_action=recommended_action,
        retry_state=retry_state,
        error_state=error_state,
    )
    advance_validated_stage(current_project, report)
    from .events import EvaluationEvent, event_log_for

    event_log_for(current_project.root).append(
        EvaluationEvent.create(
            "validation_result",
            current_project.state.project_id,
            {
                "stage_id": report.stage_id,
                "valid": report.valid,
                "issues": [issue.to_dict() for issue in report.issues],
                "attempt_number": report.attempt_number,
                "recommended_action": report.recommended_action,
                "artifact_hashes": {
                    path: artifact.sha256 for path, artifact in report.artifact_refs.items()
                },
                "retry_state": report.retry_state,
                "error_state": report.error_state,
            },
        )
    )
    return report


def advance_validated_stage(project: ResearchProject, report: ValidationReport) -> ResearchProject:
    """Atomically persist the outcome of a validation report for the current stage."""
    state = project.state
    if report.stage_id != state.current_stage:
        raise ValueError("validation report does not match the current stage")

    if not report.valid:
        retry_counts = {**state.retry_counts, str(report.stage_id): report.attempt_number}
        error_status = (
            StageStatus.BLOCKED
            if report.retry_state == "retry_limit_reached"
            else StageStatus.NEEDS_REVISION
        )
        last_error: dict[str, object] = {
            "error_class": error_status.value,
            "stage_id": report.stage_id,
            "attempt_number": report.attempt_number,
            "issues": [issue.to_dict() for issue in report.issues],
            "artifact_hashes": {
                path: artifact.sha256 for path, artifact in report.artifact_refs.items()
            },
            "recommended_action": report.recommended_action,
            "retry_state": report.retry_state,
        }
        return project.persist_state(
            replace(
                state,
                status=error_status,
                next_action=report.recommended_action,
                retry_counts=retry_counts,
                last_error=last_error,
            )
        )

    contract = get_contract(report.stage_id)
    artifacts = {**state.artifacts, **report.artifact_refs}
    if contract.requires_approval:
        updated_state = replace(
            state,
            status=StageStatus.AWAITING_APPROVAL,
            next_action="await_approval",
            artifacts=artifacts,
            last_error=None,
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
            next_action=(
                "report_synthesis_milestone_only"
                if report.stage_id == SUPPORTED_STAGE_MAX
                else "prepare_stage"
            ),
            artifacts=artifacts,
            last_error=None,
        )
    return project.persist_state(updated_state)
