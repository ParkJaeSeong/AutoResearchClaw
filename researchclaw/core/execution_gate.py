"""Passive Stage-12 readiness rechecks and execution approval bindings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import stat

from .events import EvaluationEvent, event_log_for
from .models import ArtifactRef, ProjectState, StageStatus
from .paths import resolve_project_artifact
from .persistence import atomic_write_json
from .project import ResearchProject
from .resource_planning import (
    RESOURCE_PLAN_PATH,
    hardware_drift_warnings,
    observe_local_hardware,
    validate_resource_plan_structure,
    validate_stage_eleven,
)

_HASH_CHUNK_SIZE = 1024 * 1024
_STAGE_TWELVE_ARTIFACT_PATHS = (
    "experiment/design.json",
    "experiment/package_manifest.json",
    "experiment/code/config.json",
    RESOURCE_PLAN_PATH,
)
_IMMUTABLE_ROOT_FIELDS = (
    "schema_version",
    "project_id",
    "bindings",
    "saved_hardware_profile",
    "tasks",
    "budget",
    "deferred_command",
    "result_path",
    "prohibitions",
)
_IMMUTABLE_INPUT_FIELDS = (
    "path",
    "required",
    "license_status",
    "preparation_note",
)


@dataclass(frozen=True)
class ExecutionGateStatus:
    readiness: str
    approval_eligible: bool
    unmet_prerequisites: tuple[str, ...]
    resource_plan_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "unmet_prerequisites": list(self.unmet_prerequisites),
            "resource_plan_sha256": self.resource_plan_sha256,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _immutable_projection(raw: dict[str, object]) -> dict[str, object]:
    raw_inputs = raw.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("persisted Stage 11 resource plan has malformed inputs")
    input_projection: list[dict[str, object]] = []
    for raw_input in raw_inputs:
        if not isinstance(raw_input, dict):
            raise ValueError("persisted Stage 11 resource plan has malformed inputs")
        input_projection.append(
            {field: deepcopy(raw_input.get(field)) for field in _IMMUTABLE_INPUT_FIELDS}
        )
    return {
        **{field: deepcopy(raw.get(field)) for field in _IMMUTABLE_ROOT_FIELDS},
        "inputs": input_projection,
    }


def _load_validated_resource_plan(
    project: ResearchProject,
) -> tuple[Path, dict[str, object]]:
    artifact = project.state.artifacts.get(RESOURCE_PLAN_PATH)
    if artifact is None or artifact.path != RESOURCE_PLAN_PATH:
        raise ValueError("validated Stage 11 resource plan is missing")
    try:
        path = resolve_project_artifact(project.root, RESOURCE_PLAN_PATH)
        file_stat = path.stat()
        digest = _sha256(path)
    except (OSError, ValueError) as error:
        raise ValueError(
            "resource plan changed since Stage 11 validation; return to Stage 11"
        ) from error
    if (
        not path.is_file()
        or file_stat.st_size != artifact.size
        or digest != artifact.sha256
    ):
        raise ValueError(
            "resource plan changed since Stage 11 validation; return to Stage 11"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("validated Stage 11 resource plan cannot be read") from error
    outcome = validate_resource_plan_structure(raw)
    if not outcome.valid or outcome.plan is None or not isinstance(raw, dict):
        raise ValueError("validated Stage 11 resource plan is malformed")
    return path, raw


def _refresh_input_facts(root: Path, raw_input: dict[str, object]) -> None:
    relative_path = raw_input["path"]
    try:
        path = resolve_project_artifact(root, relative_path)
        exists = path.exists()
        is_regular = exists and stat.S_ISREG(path.stat().st_mode)
        size_bytes = path.stat().st_size if is_regular else 0
        digest = _sha256(path) if is_regular else None
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError(
            f"declared input cannot be rechecked safely: {relative_path!r}"
        ) from error
    raw_input.update(
        {
            "exists": exists,
            "is_regular_file": is_regular,
            "size_bytes": size_bytes,
            "sha256": digest,
        }
    )


def _derived_warnings(
    saved_profile: object,
    observation: dict[str, object],
) -> list[str]:
    if not isinstance(saved_profile, dict):
        raise ValueError("persisted Stage 11 saved hardware profile is malformed")
    return list(hardware_drift_warnings(saved_profile, observation))


def _derived_prerequisites(
    raw: dict[str, object],
    observation: dict[str, object],
) -> list[str]:
    budget = raw["budget"]
    inputs = raw["inputs"]
    if not isinstance(budget, dict) or not isinstance(inputs, list):
        raise ValueError("persisted Stage 11 resource plan is malformed")
    prerequisites: list[str] = []
    if observation["logical_cpu_count"] < budget["peak_cpu_count"]:
        prerequisites.append(
            f"Provide at least {budget['peak_cpu_count']} logical CPU cores."
        )
    if observation["total_memory_bytes"] < budget["peak_memory_bytes"]:
        prerequisites.append(
            f"Provide at least {budget['peak_memory_bytes']} bytes of memory."
        )
    if observation["free_disk_bytes"] < budget["peak_temporary_disk_bytes"]:
        prerequisites.append(
            f"Free at least {budget['peak_temporary_disk_bytes']} bytes of project disk space."
        )
    if budget["peak_gpu_count"] and observation["gpu_available"] is not True:
        prerequisites.append(
            f"Provide at least {budget['peak_gpu_count']} available GPU."
        )
    for raw_input in inputs:
        if not isinstance(raw_input, dict) or raw_input.get("required") is not True:
            continue
        relative_path = raw_input["path"]
        if raw_input["exists"] is False:
            prerequisites.append(f"Provide required input file at {relative_path}.")
        elif raw_input["is_regular_file"] is False:
            prerequisites.append(
                f"Replace {relative_path} with a regular input file."
            )
        if raw_input["license_status"] == "unconfirmed":
            prerequisites.append(
                f"Confirm license authorization for required input {relative_path}."
            )
    return sorted(set(prerequisites))


def _current_rejection(project: ResearchProject) -> bool:
    from .approval import approval_matches_state, load_approval_record

    record = load_approval_record(project.root, 12)
    return (
        record is not None
        and record.decision == "reject"
        and approval_matches_state(project.root, project.state, record)
    )


def _recheck_execution_readiness(
    project: ResearchProject,
    *,
    allow_rejected_decision: bool,
) -> ExecutionGateStatus:
    current_project = ResearchProject.open(project.root)
    state = current_project.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("execution readiness can only be rechecked at Stage 12")
    current_rejection = _current_rejection(current_project)
    if current_rejection and not allow_rejected_decision:
        raise ValueError("execution gate is locked after a human rejection")
    if (
        state.status is not StageStatus.AWAITING_APPROVAL
        or state.next_action
        not in {"approve_experiment_execution", "report_missing_execution_inputs"}
    ):
        raise ValueError("Stage 12 execution gate is not awaiting a readiness recheck")

    path, raw = _load_validated_resource_plan(current_project)
    immutable_before = _immutable_projection(raw)
    refreshed = deepcopy(raw)
    observation = asdict(observe_local_hardware(current_project.root))
    refreshed["hardware_observation"] = observation
    raw_inputs = refreshed["inputs"]
    assert isinstance(raw_inputs, list)
    for raw_input in raw_inputs:
        assert isinstance(raw_input, dict)
        _refresh_input_facts(current_project.root, raw_input)
    refreshed["warnings"] = _derived_warnings(
        refreshed["saved_hardware_profile"], observation
    )
    prerequisites = _derived_prerequisites(refreshed, observation)
    refreshed["unmet_prerequisites"] = prerequisites
    refreshed["readiness"] = (
        "needs_input" if prerequisites else "ready_for_execution"
    )

    if _immutable_projection(refreshed) != immutable_before:
        raise ValueError(
            "resource plan structure changed during recheck; return to Stage 11"
        )
    outcome = validate_resource_plan_structure(refreshed)
    if not outcome.valid or outcome.plan is None:
        raise ValueError("refreshed resource plan is malformed; return to Stage 11")
    _plan, issues = validate_stage_eleven(current_project, refreshed)
    if issues:
        details = "; ".join(
            f"{issue.path}: {issue.message}" for issue in issues
        )
        raise ValueError(f"refreshed resource plan is invalid: {details}")

    if current_rejection and refreshed["readiness"] != "ready_for_execution":
        artifact = state.artifacts[RESOURCE_PLAN_PATH]
        return ExecutionGateStatus(
            readiness=str(refreshed["readiness"]),
            approval_eligible=False,
            unmet_prerequisites=tuple(prerequisites),
            resource_plan_sha256=artifact.sha256,
        )

    atomic_write_json(path, refreshed, prefix="resources-")
    file_stat = path.stat()
    digest = _sha256(path)
    updated_state = replace(
        state,
        status=StageStatus.AWAITING_APPROVAL,
        next_action=(
            "approve_experiment_execution"
            if refreshed["readiness"] == "ready_for_execution"
            else "report_missing_execution_inputs"
        ),
        artifacts={
            **state.artifacts,
            RESOURCE_PLAN_PATH: ArtifactRef(
                path=RESOURCE_PLAN_PATH,
                sha256=digest,
                size=file_stat.st_size,
            ),
        },
        last_error=None,
    )
    current_project.persist_state(updated_state)
    status = ExecutionGateStatus(
        readiness=str(refreshed["readiness"]),
        approval_eligible=refreshed["readiness"] == "ready_for_execution",
        unmet_prerequisites=tuple(prerequisites),
        resource_plan_sha256=digest,
    )
    event_log_for(current_project.root).append(
        EvaluationEvent.create(
            "execution_readiness_rechecked",
            state.project_id,
            status.to_dict(),
        )
    )
    return status


def recheck_execution_readiness(project: ResearchProject) -> ExecutionGateStatus:
    """Refresh passive facts unless a current human rejection locks the gate."""
    from .handoff import normalize_durable_project

    current_project = normalize_durable_project(project)
    return _recheck_execution_readiness(
        current_project,
        allow_rejected_decision=False,
    )


def _stage_twelve_artifact_hashes(
    root: Path,
    state: ProjectState,
) -> dict[str, str]:
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("Stage 12 execution approval artifacts are unavailable")
    hashes: dict[str, str] = {}
    for relative_path in _STAGE_TWELVE_ARTIFACT_PATHS:
        artifact = state.artifacts.get(relative_path)
        if artifact is None or artifact.path != relative_path:
            raise ValueError(f"persisted artifact hash is missing for {relative_path}")
        path = resolve_project_artifact(root, relative_path)
        file_stat = path.stat()
        digest = _sha256(path)
        if (
            not path.is_file()
            or file_stat.st_size != artifact.size
            or digest != artifact.sha256
        ):
            raise ValueError(f"artifact has changed since validation: {relative_path}")
        hashes[relative_path] = digest
    return hashes


def stage_twelve_artifact_hashes(project: ResearchProject) -> dict[str, str]:
    """Hash the exact four artifacts against the current durable Stage-12 state."""
    current_project = ResearchProject.open(project.root)
    return _stage_twelve_artifact_hashes(
        current_project.root,
        current_project.state,
    )
