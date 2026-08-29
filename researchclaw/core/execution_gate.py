"""Passive Stage-12 readiness rechecks and execution approval bindings."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType

from .events import EvaluationEvent, event_log_for
from .models import ArtifactRef, ProjectState, StageStatus
from .paths import resolve_project_artifact, validate_relative_path
from .persistence import atomic_write_json
from .project import ResearchProject
from .resource_planning import (
    RESOURCE_PLAN_PATH,
    hardware_drift_warnings,
    observe_local_hardware,
    validate_resource_plan_structure,
    validate_stage_eleven,
)
from .transactions import project_mutation

_HASH_CHUNK_SIZE = 1024 * 1024
_MAX_RESOURCE_PLAN_BYTES = 1024 * 1024
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


@dataclass(frozen=True)
class DevelopmentInputStatus:
    readiness: str
    approval_eligible: bool
    unmet_prerequisites: tuple[str, ...]
    input_manifest_path: str
    input_manifest_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "unmet_prerequisites": list(self.unmet_prerequisites),
            "input_manifest_path": self.input_manifest_path,
            "input_manifest_sha256": self.input_manifest_sha256,
        }


@dataclass(frozen=True)
class ValidatedDevelopmentInput:
    manifest_path: str
    manifest_sha256: str
    manifest: Mapping[str, object]
    cell_rows: tuple[Mapping[str, str], ...]
    feature_rows: tuple[Mapping[str, str], ...]


class DevelopmentInputValidationError(ValueError):
    """Validation failure retaining only bounded manifest identity metadata."""

    def __init__(
        self,
        message: str,
        *,
        manifest_path: str | None = None,
        manifest_sha256: str | None = None,
    ) -> None:
        super().__init__(message)
        self.manifest_path = manifest_path
        self.manifest_sha256 = manifest_sha256


@dataclass(frozen=True)
class ProjectFileIdentity:
    """A regular project's stable size and streaming SHA-256 identity."""

    size: int
    sha256: str


def _open_project_file_descriptor(root: Path, relative_path: object) -> tuple[int, str]:
    """Open one regular project file through a no-symlink openat chain."""
    value = validate_relative_path(relative_path, kind="artifact")
    resolve_project_artifact(root, value)
    parts = Path(value).parts
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(Path(root).resolve(strict=True), directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(
                part,
                directory_flags | nofollow,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | nofollow | nonblock,
            dir_fd=descriptor,
        )
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(file_descriptor)
            raise ValueError(f"project file is not regular: {value}")
        return file_descriptor, value
    finally:
        os.close(descriptor)


def _project_file_identity(root: Path, relative_path: object) -> ProjectFileIdentity:
    """Hash a regular project file without retaining its contents in memory."""
    descriptor, _value = _open_project_file_descriptor(root, relative_path)
    try:
        initial = os.fstat(descriptor)
        digest = hashlib.sha256()
        observed_size = 0
        while chunk := os.read(descriptor, _HASH_CHUNK_SIZE):
            observed_size += len(chunk)
            digest.update(chunk)
        final = os.fstat(descriptor)
        if (
            observed_size != initial.st_size
            or final.st_size != initial.st_size
            or final.st_mtime_ns != initial.st_mtime_ns
            or final.st_ctime_ns != initial.st_ctime_ns
        ):
            raise ValueError("project file changed while hashing")
        return ProjectFileIdentity(size=observed_size, sha256=digest.hexdigest())
    finally:
        os.close(descriptor)


def _read_project_file_snapshot(
    root: Path,
    relative_path: object,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read a bounded regular project file through a no-symlink openat chain."""
    if max_bytes is not None and (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes < 0
    ):
        raise ValueError("max_bytes must be a non-negative integer")
    descriptor, value = _open_project_file_descriptor(root, relative_path)
    try:
        initial = os.fstat(descriptor)
        if max_bytes is not None and initial.st_size > max_bytes:
            raise ValueError(f"project file exceeds byte limit: {value}")
        chunks: list[bytes] = []
        observed_size = 0
        while chunk := os.read(descriptor, _HASH_CHUNK_SIZE):
            observed_size += len(chunk)
            if max_bytes is not None and observed_size > max_bytes:
                raise ValueError(f"project file exceeds byte limit: {value}")
            chunks.append(chunk)
        final = os.fstat(descriptor)
        if (
            observed_size != initial.st_size
            or final.st_size != initial.st_size
            or final.st_mtime_ns != initial.st_mtime_ns
            or final.st_ctime_ns != initial.st_ctime_ns
        ):
            raise ValueError("project file changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


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
        payload = _read_project_file_snapshot(
            project.root,
            RESOURCE_PLAN_PATH,
            max_bytes=_MAX_RESOURCE_PLAN_BYTES,
        )
        digest = hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError) as error:
        raise ValueError(
            "resource plan changed since Stage 11 validation; return to Stage 11"
        ) from error
    if (
        len(payload) != artifact.size
        or digest != artifact.sha256
    ):
        raise ValueError(
            "resource plan changed since Stage 11 validation; return to Stage 11"
        )
    try:
        raw = json.loads(payload.decode("utf-8"))
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
        identity = _project_file_identity(root, relative_path) if is_regular else None
        size_bytes = identity.size if identity is not None else 0
        digest = identity.sha256 if identity is not None else None
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
    allow_preexisting_result: bool = False,
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
    if allow_preexisting_result:
        issues = tuple(issue for issue in issues if issue.code != "preexisting_result")
    if issues:
        details = "; ".join(
            f"{issue.path}: {issue.message}" for issue in issues
        )
        raise ValueError(f"refreshed resource plan is invalid: {details}")

    if allow_preexisting_result:
        artifact = state.artifacts[RESOURCE_PLAN_PATH]
        status = ExecutionGateStatus(
            readiness=str(refreshed["readiness"]),
            approval_eligible=refreshed["readiness"] == "ready_for_execution",
            unmet_prerequisites=tuple(prerequisites),
            resource_plan_sha256=artifact.sha256,
        )
        event_log_for(current_project.root).append(
            EvaluationEvent.create(
                "execution_readiness_rechecked",
                state.project_id,
                status.to_dict(),
            )
        )
        return status

    if current_rejection and refreshed["readiness"] != "ready_for_execution":
        artifact = state.artifacts[RESOURCE_PLAN_PATH]
        return ExecutionGateStatus(
            readiness=str(refreshed["readiness"]),
            approval_eligible=False,
            unmet_prerequisites=tuple(prerequisites),
            resource_plan_sha256=artifact.sha256,
        )

    atomic_write_json(path, refreshed, prefix="resources-")
    identity = _project_file_identity(current_project.root, RESOURCE_PLAN_PATH)
    digest = identity.sha256
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
                size=identity.size,
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


@project_mutation
def recheck_execution_readiness(project: ResearchProject) -> ExecutionGateStatus:
    """Refresh passive facts unless a current human rejection locks the gate."""
    from .handoff import normalize_durable_project

    current_project = normalize_durable_project(project)
    return _recheck_execution_readiness(
        current_project,
        allow_rejected_decision=False,
    )


def _development_artifact(
    root: Path,
    manifest_section: object,
    section_name: str,
) -> list[dict[str, str]]:
    if not isinstance(manifest_section, dict):
        raise ValueError(f"development manifest {section_name} must be an object")
    relative_path = manifest_section.get("path")
    expected_rows = manifest_section.get("row_count")
    expected_sha256 = manifest_section.get("sha256")
    if (
        not isinstance(relative_path, str)
        or not isinstance(expected_rows, int)
        or isinstance(expected_rows, bool)
        or expected_rows < 1
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        raise ValueError(
            f"development manifest {section_name} must declare path, positive row_count, and sha256"
        )
    try:
        payload = _read_project_file_snapshot(root, relative_path)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(
            f"development manifest {section_name} path must be project-relative"
        ) from error
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError(f"development input sha256 mismatch: {relative_path}")
    try:
        text = payload.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = reader.fieldnames
        rows = list(reader)
    except (UnicodeError, csv.Error) as error:
        raise ValueError(
            f"development input must be readable CSV: {relative_path}"
        ) from error
    if (
        not fieldnames
        or any(not isinstance(field, str) or not field for field in fieldnames)
        or len(set(fieldnames)) != len(fieldnames)
        or any(
            set(row) != set(fieldnames)
            or any(not isinstance(value, str) for value in row.values())
            for row in rows
        )
    ):
        raise ValueError(
            f"development input must have consistent named columns: {relative_path}"
        )
    if len(rows) != expected_rows:
        raise ValueError(
            f"development input row_count mismatch: {relative_path}"
        )
    return rows


def _validate_development_structure(
    manifest: dict[str, object],
    cell_rows: list[dict[str, str]],
    feature_rows: list[dict[str, str]],
) -> None:
    cutoff = manifest.get("feature_cutoff")
    if cutoff is None:
        return
    if not isinstance(cutoff, dict):
        raise ValueError("development feature cutoff must be an object")
    cutoff_field = cutoff.get("cutoff_field")
    cycle_field = cutoff.get("measurement_cycle_field")
    if not isinstance(cutoff_field, str) or not isinstance(cycle_field, str):
        raise ValueError("development feature cutoff fields are required")
    required_cell_fields = {
        "dataset_id",
        "condition_id",
        "cell_id",
        "split_role",
        cutoff_field,
        "cycle_life_cycles",
    }
    required_feature_fields = {
        "dataset_id",
        "condition_id",
        "cell_id",
        cycle_field,
    }
    if not cell_rows or not required_cell_fields.issubset(cell_rows[0]):
        raise ValueError("development cell records are missing structural fields")
    if not feature_rows or not required_feature_fields.issubset(feature_rows[0]):
        raise ValueError("development features are missing structural fields")
    declared_dataset_ids: list[str] = []
    datasets = manifest["datasets"]
    if not isinstance(datasets, list):
        raise ValueError("development input datasets must be an array")
    for entry in datasets:
        if not isinstance(entry, dict):
            raise ValueError("development input dataset entry must be an object")
        dataset_id = entry.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("development input dataset_id must be non-empty")
        if dataset_id in declared_dataset_ids:
            raise ValueError(f"development input dataset_id is duplicated: {dataset_id}")
        declared_dataset_ids.append(dataset_id)
    cells: dict[str, dict[str, str]] = {}
    group_splits: dict[tuple[str, str], str] = {}
    for row in cell_rows:
        cell_id = row["cell_id"]
        if cell_id in cells:
            raise ValueError(f"development cell_id is duplicated: {cell_id}")
        cells[cell_id] = row
        group_key = (row["dataset_id"], row["condition_id"])
        prior_split = group_splits.setdefault(group_key, row["split_role"])
        if prior_split != row["split_role"]:
            raise ValueError("development condition group crosses split roles")
        try:
            if int(row["cycle_life_cycles"]) <= int(row[cutoff_field]):
                raise ValueError("development label must occur after feature cutoff")
        except (TypeError, ValueError) as error:
            if str(error).startswith("development label"):
                raise
            raise ValueError("development cell cutoff and label must be integers") from error
    seen_cycles: set[tuple[str, str]] = set()
    for row in feature_rows:
        cell_id = row["cell_id"]
        cell = cells.get(cell_id)
        if cell is None:
            raise ValueError(f"development feature has unknown cell_id: {cell_id}")
        if (
            row["dataset_id"] != cell["dataset_id"]
            or row["condition_id"] != cell["condition_id"]
        ):
            raise ValueError(f"development feature keys disagree for cell: {cell_id}")
        try:
            cycle_index = int(row[cycle_field])
            cutoff_cycle = int(cell[cutoff_field])
        except (TypeError, ValueError) as error:
            raise ValueError("development feature cycle and cutoff must be integers") from error
        if cycle_index > cutoff_cycle:
            raise ValueError(f"development feature cutoff violated for cell: {cell_id}")
        cycle_key = (cell_id, str(cycle_index))
        if cycle_key in seen_cycles:
            raise ValueError(f"development cell-cycle is duplicated: {cell_id}")
        seen_cycles.add(cycle_key)
    declared = set(declared_dataset_ids)
    cell_datasets = {row["dataset_id"] for row in cell_rows}
    feature_datasets = {row["dataset_id"] for row in feature_rows}
    unexpected = sorted((cell_datasets | feature_datasets) - declared)
    if unexpected:
        raise ValueError(f"development input has unexpected row dataset: {unexpected[0]}")
    missing = sorted(declared - cell_datasets)
    if missing:
        raise ValueError(f"development declared dataset has no rows: {missing[0]}")
    if feature_datasets != declared:
        missing_features = sorted(declared - feature_datasets)
        raise ValueError(
            f"development declared dataset has no feature rows: {missing_features[0]}"
        )


@project_mutation
def validate_development_input(
    project: ResearchProject,
    input_manifest_path: str,
    *,
    record_event: bool = True,
) -> tuple[DevelopmentInputStatus, ValidatedDevelopmentInput]:
    """Validate an explicit synthetic fixture without changing the execution gate."""
    from .handoff import require_current_durable_project

    current_project = require_current_durable_project(project)
    state = current_project.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("development input can only be rechecked at Stage 12")
    if not isinstance(input_manifest_path, str) or not input_manifest_path:
        raise ValueError("development input manifest path must be project-relative")
    try:
        manifest_bytes = _read_project_file_snapshot(
            current_project.root, input_manifest_path
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(
            "development input manifest path must be project-relative"
        ) from error
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        required = {
            "schema_version",
            "datasets",
            "cell_records",
            "features",
            "labels",
            "groups",
            "provenance",
        }
        if not isinstance(manifest, dict) or not required.issubset(manifest):
            raise ValueError("development input manifest is missing required fields")
        if manifest.get("manifest_type") != "synthetic_development_input":
            raise ValueError("development input must declare synthetic_development_input")
        if manifest.get("evidence_eligible") is not False:
            raise ValueError("development input must not be evidence eligible")
        provenance = manifest.get("provenance")
        if (
            not isinstance(provenance, dict)
            or provenance.get("license_status") != "not_required_synthetic"
            or provenance.get("research_evidence_use") is not False
        ):
            raise ValueError(
                "development input provenance must prohibit research evidence use"
            )
        datasets = manifest.get("datasets")
        if not isinstance(datasets, list) or not datasets:
            raise ValueError("development input must declare at least one dataset")
        cell_rows = _development_artifact(
            current_project.root,
            manifest["cell_records"],
            "cell_records",
        )
        feature_rows = _development_artifact(
            current_project.root,
            manifest["features"],
            "features",
        )
        _validate_development_structure(manifest, cell_rows, feature_rows)
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        message = (
            "development input manifest must be valid JSON"
            if isinstance(error, (UnicodeError, json.JSONDecodeError))
            else str(error)
        )
        raise DevelopmentInputValidationError(
            message,
            manifest_path=input_manifest_path,
            manifest_sha256=digest,
        ) from error
    status = DevelopmentInputStatus(
        readiness="ready_for_development",
        approval_eligible=False,
        unmet_prerequisites=(),
        input_manifest_path=input_manifest_path,
        input_manifest_sha256=digest,
    )
    if record_event:
        event_log_for(current_project.root).append(
            EvaluationEvent.create(
                "development_input_rechecked",
                state.project_id,
                status.to_dict(),
            )
        )
    validated = ValidatedDevelopmentInput(
        manifest_path=input_manifest_path,
        manifest_sha256=digest,
        manifest=_freeze_json(manifest),
        cell_rows=tuple(_freeze_json(row) for row in cell_rows),
        feature_rows=tuple(_freeze_json(row) for row in feature_rows),
    )
    return status, validated


@project_mutation
def recheck_development_input(
    project: ResearchProject,
    input_manifest_path: str,
) -> DevelopmentInputStatus:
    """Validate an explicit synthetic fixture without changing the execution gate."""
    status, _validated = validate_development_input(project, input_manifest_path)
    return status


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
        identity = _project_file_identity(root, relative_path)
        digest = identity.sha256
        if (
            identity.size != artifact.size
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
