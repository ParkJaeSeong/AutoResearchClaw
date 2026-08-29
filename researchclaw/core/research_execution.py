"""Explicit, non-executing Stage-12 research execution handoffs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from types import MappingProxyType

from .approval import ApprovalRecord, approval_matches_state
from .execution_gate import (
    _load_validated_resource_plan,
    _read_project_file_snapshot,
    stage_twelve_artifact_hashes,
)
from .events import EvaluationEvent, event_log_for
from .models import ArtifactRef, ProjectState, StageStatus
from .paths import resolve_project_artifact
from .persistence import _fsync_directory, atomic_write_json
from .project import ResearchProject
from .resource_planning import RESOURCE_PLAN_PATH, validate_stage_eleven


EXECUTION_CONTRACT_PATH = "experiment/execution_contract.json"
RESEARCH_RESULT_PATH = "experiment/results.json"
_PACKAGE_MANIFEST_PATH = "experiment/package_manifest.json"
_STAGE_TWELVE_APPROVAL_PATH = "approvals/stage-12.json"
_REGISTRATION_LOCK_PATH = "evaluation/events.jsonl"
_REGISTRATION_PENDING_PATH = (
    ".researchclaw/research-result-registration.pending.json"
)
_APPROVAL_FIELDS = frozenset(
    {
        "schema_version",
        "project_id",
        "stage_id",
        "decision",
        "artifact_hashes",
        "decided_at",
        "note",
    }
)
_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "contract_id",
        "project_id",
        "created_at",
        "command",
        "result_path",
        "bindings",
        "inputs",
        "prohibitions",
        "result_template",
    }
)
_RESULT_TEMPLATE: dict[str, object] = {
    "schema_version": 1,
    "required_fields": [
        "schema_version",
        "project_id",
        "execution_contract",
        "development_only",
        "evidence_eligible",
        "status",
        "metrics",
        "split_summary",
        "provenance",
        "runtime",
    ],
    "status": "completed",
    "development_only": False,
    "evidence_eligible": True,
}
_REGISTRATION_ERROR_CATEGORIES = frozenset(
    {
        "execution_approval_invalid",
        "execution_prerequisites_changed",
        "execution_contract_invalid",
        "execution_contract_stale",
        "research_result_file_invalid",
        "research_result_schema_invalid",
        "research_result_project_mismatch",
        "research_result_contract_mismatch",
        "research_result_provenance_mismatch",
        "research_result_split_invalid",
        "research_result_leakage_detected",
        "research_result_metrics_invalid",
        "development_result_not_registerable",
        "research_result_registration_conflict",
        "research_result_registration_recovery_invalid",
    }
)


@dataclass(frozen=True)
class ExecutionPreparationStatus:
    readiness: str
    approval_eligible: bool
    command: str
    result_path: str
    contract_path: str
    contract_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedResearchResult:
    result_path: str
    result_sha256: str
    payload: Mapping[str, object]
    metric_count: int
    input_count: int


@dataclass(frozen=True)
class ResearchResultRegistrationStatus:
    readiness: str
    approval_eligible: bool
    result_path: str
    result_sha256: str
    current_stage: int
    next_action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _PendingResearchResultRegistration:
    project_id: str
    result_path: str
    result_sha256: str
    result_size: int
    prior_state: ProjectState
    target_state: ProjectState
    success_event: EvaluationEvent

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "project_id": self.project_id,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "result_size": self.result_size,
            "prior_state": self.prior_state.to_dict(),
            "target_state": self.target_state.to_dict(),
            "success_event": self.success_event.to_dict(),
        }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _current_project(project: ResearchProject) -> ResearchProject:
    return ResearchProject.open(project.root)


def _load_strict_stage_twelve_approval(project: ResearchProject) -> ApprovalRecord:
    try:
        payload = _read_project_file_snapshot(
            project.root, _STAGE_TWELVE_APPROVAL_PATH
        )
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise ValueError("execution_approval_invalid") from error
    if not isinstance(raw, dict) or set(raw) != _APPROVAL_FIELDS:
        raise ValueError("execution_approval_invalid")
    artifact_hashes = raw["artifact_hashes"]
    if (
        type(raw["schema_version"]) is not int
        or raw["schema_version"] != 1
        or not isinstance(raw["project_id"], str)
        or type(raw["stage_id"]) is not int
        or raw["stage_id"] != 12
        or not isinstance(raw["decision"], str)
        or raw["decision"] not in {"approve", "reject"}
        or not isinstance(artifact_hashes, dict)
        or not isinstance(raw["decided_at"], str)
        or not isinstance(raw["note"], str)
    ):
        raise ValueError("execution_approval_invalid")
    for path, digest in artifact_hashes.items():
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("execution_approval_invalid")
        try:
            resolve_project_artifact(project.root, path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_approval_invalid") from error
    return ApprovalRecord(
        schema_version=raw["schema_version"],
        project_id=raw["project_id"],
        stage_id=raw["stage_id"],
        decision=raw["decision"],
        artifact_hashes=dict(artifact_hashes),
        decided_at=raw["decided_at"],
        note=raw["note"],
    )


def _load_current_stage_twelve_approval(project: ResearchProject) -> ApprovalRecord:
    """Require a current, explicit Stage-12 approval."""
    current = _current_project(project)
    state = current.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("execution_approval_invalid")
    record = _load_strict_stage_twelve_approval(current)
    if (
        record is None
        or record.decision != "approve"
        or not approval_matches_state(current.root, state, record)
    ):
        raise ValueError("execution_approval_invalid")
    return record


def _load_current_resource_plan(
    project: ResearchProject, *, allow_result: bool = False
) -> dict[str, object]:
    """Reopen and revalidate the persisted Stage-11 resource plan."""
    current = _current_project(project)
    try:
        _path, raw = _load_validated_resource_plan(current)
        _plan, issues = validate_stage_eleven(current, raw)
    except (OSError, ValueError, TypeError) as error:
        raise ValueError("execution_prerequisites_changed") from error
    if allow_result:
        issues = tuple(issue for issue in issues if issue.code != "preexisting_result")
    if issues:
        raise ValueError("execution_prerequisites_changed")
    if (
        raw.get("readiness") != "ready_for_execution"
        or raw.get("unmet_prerequisites") != []
    ):
        raise ValueError("execution_prerequisites_changed")
    if raw.get("result_path") != RESEARCH_RESULT_PATH:
        raise ValueError("execution_prerequisites_changed")
    return raw


def _snapshot_required_inputs(
    project: ResearchProject, plan: Mapping[str, object]
) -> list[dict[str, object]]:
    """Return sorted snapshots of declared, required, regular input files."""
    raw_inputs = plan.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("execution_prerequisites_changed")
    snapshots: list[dict[str, object]] = []
    for raw_input in raw_inputs:
        if not isinstance(raw_input, Mapping) or raw_input.get("required") is not True:
            continue
        path = raw_input.get("path")
        license_status = raw_input.get("license_status")
        declared_size = raw_input.get("size_bytes")
        declared_digest = raw_input.get("sha256")
        if (
            not isinstance(path, str)
            or license_status not in {"confirmed", "not_required"}
            or not isinstance(declared_size, int)
            or isinstance(declared_size, bool)
            or not isinstance(declared_digest, str)
            or raw_input.get("exists") is not True
            or raw_input.get("is_regular_file") is not True
        ):
            raise ValueError("execution_prerequisites_changed")
        try:
            snapshot = _read_project_file_snapshot(project.root, path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_prerequisites_changed") from error
        digest = _sha256(snapshot)
        if len(snapshot) != declared_size or digest != declared_digest:
            raise ValueError("execution_prerequisites_changed")
        snapshots.append(
            {
                "path": path,
                "size_bytes": len(snapshot),
                "sha256": digest,
                "license_status": license_status,
            }
        )
    return sorted(snapshots, key=lambda item: str(item["path"]))


def _package_file_bindings(project: ResearchProject) -> list[dict[str, str]]:
    try:
        manifest_bytes = _read_project_file_snapshot(
            project.root, _PACKAGE_MANIFEST_PATH
        )
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("execution_approval_invalid") from error
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), list):
        raise ValueError("execution_approval_invalid")

    bindings: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, Mapping):
            raise ValueError("execution_approval_invalid")
        path = entry.get("path")
        expected_digest = entry.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(expected_digest, str)
            or len(expected_digest) != 64
            or path in seen_paths
        ):
            raise ValueError("execution_approval_invalid")
        seen_paths.add(path)
        try:
            payload = _read_project_file_snapshot(project.root, path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_approval_invalid") from error
        actual_digest = _sha256(payload)
        if actual_digest != expected_digest:
            raise ValueError("execution_approval_invalid")
        bindings.append({"path": path, "sha256": actual_digest})
    return sorted(bindings, key=lambda item: item["path"])


def _contract_id_payload(contract: Mapping[str, object]) -> dict[str, object]:
    return {
        key: contract[key]
        for key in (
            "project_id",
            "command",
            "result_path",
            "bindings",
            "inputs",
            "prohibitions",
            "result_template",
        )
    }


def _build_execution_contract(
    project: ResearchProject, *, allow_result: bool = False
) -> dict[str, object]:
    """Return a closed contract whose identity binds the current approved inputs."""
    current = _current_project(project)
    hashes = stage_twelve_artifact_hashes(current)
    plan = _load_current_resource_plan(current, allow_result=allow_result)
    command = plan.get("deferred_command")
    raw_prohibitions = plan.get("prohibitions")
    if not isinstance(command, str) or not command or not isinstance(raw_prohibitions, Mapping):
        raise ValueError("execution_prerequisites_changed")
    if hashes.get(RESOURCE_PLAN_PATH) != _sha256(
        _read_project_file_snapshot(current.root, RESOURCE_PLAN_PATH)
    ):
        raise ValueError("execution_approval_invalid")

    required_bindings = {
        "design": "experiment/design.json",
        "package_manifest": _PACKAGE_MANIFEST_PATH,
        "config": "experiment/code/config.json",
        "resources": RESOURCE_PLAN_PATH,
    }
    bindings: dict[str, object] = {}
    for name, path in required_bindings.items():
        digest = hashes.get(path)
        if digest is None:
            raise ValueError("execution_approval_invalid")
        payload = _read_project_file_snapshot(current.root, path)
        if _sha256(payload) != digest:
            raise ValueError("execution_approval_invalid")
        bindings[name] = {"path": path, "sha256": digest}
    bindings["package_files"] = _package_file_bindings(current)

    prohibitions = dict(raw_prohibitions)
    if not all(isinstance(value, bool) and value is False for value in prohibitions.values()):
        raise ValueError("execution_prerequisites_changed")
    prohibitions["researchclaw_managed_execution"] = False
    contract: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "",
        "project_id": current.state.project_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "result_path": RESEARCH_RESULT_PATH,
        "bindings": bindings,
        "inputs": _snapshot_required_inputs(current, plan),
        "prohibitions": prohibitions,
        "result_template": _RESULT_TEMPLATE,
    }
    contract["contract_id"] = _sha256(_canonical_json(_contract_id_payload(contract)))
    return contract


def _existing_current_contract(
    project: ResearchProject,
    candidate: Mapping[str, object],
    *,
    stale_category: bool = False,
) -> bytes | None:
    path = project.root / EXECUTION_CONTRACT_PATH
    if not path.exists():
        return None
    try:
        payload = _read_project_file_snapshot(project.root, EXECUTION_CONTRACT_PATH)
        existing = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("execution_contract_invalid") from error
    artifact = project.state.artifacts.get(EXECUTION_CONTRACT_PATH)
    if artifact is None or (
        artifact.path != EXECUTION_CONTRACT_PATH
        or artifact.size != len(payload)
        or artifact.sha256 != _sha256(payload)
    ):
        raise ValueError("execution_contract_invalid")
    if (
        not isinstance(existing, dict)
        or set(existing) != _CONTRACT_FIELDS
        or _canonical_json(existing) != payload
    ):
        raise ValueError("execution_contract_invalid")
    if not isinstance(existing.get("created_at"), str) or not existing["created_at"]:
        raise ValueError("execution_contract_invalid")
    if existing.get("contract_id") != candidate.get("contract_id"):
        raise ValueError(
            "execution_contract_stale" if stale_category else "execution_contract_invalid"
        )
    if existing.get("contract_id") != _sha256(
        _canonical_json(_contract_id_payload(existing))
    ):
        raise ValueError("execution_contract_invalid")
    for field, value in candidate.items():
        if field != "created_at" and existing.get(field) != value:
            raise ValueError(
                "execution_contract_stale"
                if stale_category
                else "execution_contract_invalid"
            )
    return payload


def _reject_duplicate_keys(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError("non-finite JSON constant")


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _is_non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _expected_isolation_key(
    project: ResearchProject, contract: Mapping[str, object]
) -> str:
    bindings = contract.get("bindings")
    config_binding = bindings.get("config") if isinstance(bindings, Mapping) else None
    if not isinstance(config_binding, Mapping):
        raise ValueError("execution_contract_invalid")
    config_path = config_binding.get("path")
    config_digest = config_binding.get("sha256")
    if not isinstance(config_path, str) or not isinstance(config_digest, str):
        raise ValueError("execution_contract_invalid")
    try:
        config_bytes = _read_project_file_snapshot(project.root, config_path)
        config = json.loads(
            config_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("execution_contract_stale") from error
    if _sha256(config_bytes) != config_digest or not isinstance(config, Mapping):
        raise ValueError("execution_contract_stale")
    split_strategy = config.get("split_strategy")
    isolation_key = (
        split_strategy.get("isolation_key")
        if isinstance(split_strategy, Mapping)
        else None
    )
    if not isinstance(isolation_key, str) or not isolation_key:
        raise ValueError("execution_contract_stale")
    return isolation_key


def _validate_result_metrics(metrics: object) -> int:
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("research_result_metrics_invalid")
    for metric_key, metric in metrics.items():
        if (
            not isinstance(metric_key, str)
            or not metric_key
            or not isinstance(metric, dict)
            or set(metric) != {"name", "value", "unit"}
        ):
            raise ValueError("research_result_metrics_invalid")
        name = metric["name"]
        unit = metric["unit"]
        value = metric["value"]
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(unit, str)
            or not unit
            or not _is_finite_number(value)
        ):
            raise ValueError("research_result_metrics_invalid")
    return len(metrics)


def _validate_result_splits(split_summary: object, isolation_key: str) -> None:
    expected_split_fields = {
        "isolation_key",
        "roles",
        "cell_overlap_count",
        "group_overlap_count",
        "leakage_count",
    }
    if not isinstance(split_summary, dict) or set(split_summary) != expected_split_fields:
        raise ValueError("research_result_split_invalid")
    roles = split_summary["roles"]
    if (
        split_summary["isolation_key"] != isolation_key
        or not isinstance(roles, dict)
        or set(roles) != {"train", "validation", "calibration", "test"}
    ):
        raise ValueError("research_result_split_invalid")
    for role in roles.values():
        if (
            not isinstance(role, dict)
            or set(role) != {"cell_count", "group_count"}
            or not _is_non_negative_integer(role["cell_count"])
            or not _is_non_negative_integer(role["group_count"])
        ):
            raise ValueError("research_result_split_invalid")
    leakage_values = (
        split_summary["cell_overlap_count"],
        split_summary["group_overlap_count"],
        split_summary["leakage_count"],
    )
    if not all(_is_non_negative_integer(value) for value in leakage_values):
        raise ValueError("research_result_split_invalid")
    if any(value != 0 for value in leakage_values):
        raise ValueError("research_result_leakage_detected")


def _validate_result_runtime(runtime: object, approved_maximum: object) -> None:
    if not isinstance(runtime, dict) or set(runtime) != {
        "elapsed_seconds",
        "maximum_seconds",
    }:
        raise ValueError("research_result_schema_invalid")
    elapsed = runtime["elapsed_seconds"]
    maximum = runtime["maximum_seconds"]
    if (
        not _is_finite_number(elapsed)
        or elapsed < 0
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or maximum <= 0
        or not isinstance(approved_maximum, int)
        or isinstance(approved_maximum, bool)
        or approved_maximum <= 0
        or elapsed > maximum
        or maximum > approved_maximum
    ):
        raise ValueError("research_result_schema_invalid")


def _record_contract_artifact(project: ResearchProject, payload: bytes) -> None:
    artifact = ArtifactRef(
        path=EXECUTION_CONTRACT_PATH,
        sha256=_sha256(payload),
        size=len(payload),
    )
    if project.state.artifacts.get(EXECUTION_CONTRACT_PATH) == artifact:
        return
    project.persist_state(
        replace(
            project.state,
            artifacts={**project.state.artifacts, EXECUTION_CONTRACT_PATH: artifact},
        )
    )


def prepare_research_execution(project: ResearchProject) -> ExecutionPreparationStatus:
    """Write an approved immutable handoff without importing or running project code."""
    current = _current_project(project)
    _load_current_stage_twelve_approval(current)
    contract = _build_execution_contract(current)
    existing = _existing_current_contract(current, contract)
    if existing is None:
        path = resolve_project_artifact(current.root, EXECUTION_CONTRACT_PATH)
        atomic_write_json(
            path,
            contract,
            prefix="execution-contract-",
            compact=True,
        )
        try:
            existing = _read_project_file_snapshot(current.root, EXECUTION_CONTRACT_PATH)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_contract_invalid") from error
    _record_contract_artifact(_current_project(current), existing)
    return ExecutionPreparationStatus(
        readiness="ready_for_explicit_execution",
        approval_eligible=False,
        command=str(contract["command"]),
        result_path=RESEARCH_RESULT_PATH,
        contract_path=EXECUTION_CONTRACT_PATH,
        contract_sha256=_sha256(existing),
    )


def validate_research_result(
    project: ResearchProject, result_path: str
) -> ValidatedResearchResult:
    """Return a validated result snapshot without mutating project state or events."""
    if result_path == "experiment/dev_results.json":
        raise ValueError("development_result_not_registerable")
    if result_path != RESEARCH_RESULT_PATH:
        raise ValueError("research_result_file_invalid")
    current = _current_project(project)
    _load_current_stage_twelve_approval(current)
    resource_plan = _load_current_resource_plan(current, allow_result=True)
    contract_bytes = _existing_current_contract(
        current,
        _build_execution_contract(current, allow_result=True),
        stale_category=True,
    )
    if contract_bytes is None:
        raise ValueError("execution_contract_invalid")
    contract = json.loads(contract_bytes.decode("utf-8"))
    try:
        result_bytes = _read_project_file_snapshot(current.root, result_path)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("research_result_file_invalid") from error
    try:
        payload = json.loads(
            result_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("research_result_schema_invalid") from error

    root_fields = {
        "schema_version",
        "project_id",
        "execution_contract",
        "development_only",
        "evidence_eligible",
        "status",
        "metrics",
        "split_summary",
        "provenance",
        "runtime",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != root_fields
        or not isinstance(payload["schema_version"], int)
        or payload["schema_version"] != 1
        or isinstance(payload["schema_version"], bool)
    ):
        raise ValueError("research_result_schema_invalid")
    if payload["development_only"] is not False or payload["evidence_eligible"] is not True:
        raise ValueError("development_result_not_registerable")
    if payload["project_id"] != current.state.project_id:
        raise ValueError("research_result_project_mismatch")
    if payload["status"] != "completed":
        raise ValueError("research_result_schema_invalid")

    result_contract = payload["execution_contract"]
    if not isinstance(result_contract, dict) or set(result_contract) != {
        "path",
        "contract_id",
        "sha256",
    }:
        raise ValueError("research_result_schema_invalid")
    if (
        result_contract["path"] != EXECUTION_CONTRACT_PATH
        or result_contract["contract_id"] != contract.get("contract_id")
        or result_contract["sha256"] != _sha256(contract_bytes)
    ):
        raise ValueError("research_result_contract_mismatch")

    metric_count = _validate_result_metrics(payload["metrics"])
    _validate_result_splits(
        payload["split_summary"], _expected_isolation_key(current, contract)
    )
    provenance = payload["provenance"]
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"bindings", "inputs"}
        or provenance["bindings"] != contract.get("bindings")
        or provenance["inputs"] != contract.get("inputs")
    ):
        raise ValueError("research_result_provenance_mismatch")
    budget = resource_plan.get("budget")
    approved_maximum = (
        budget.get("total_estimated_duration_seconds")
        if isinstance(budget, Mapping)
        else None
    )
    _validate_result_runtime(payload["runtime"], approved_maximum)

    inputs = contract.get("inputs")
    frozen_payload = _freeze_json(payload)
    assert isinstance(frozen_payload, Mapping)
    return ValidatedResearchResult(
        result_path=result_path,
        result_sha256=_sha256(result_bytes),
        payload=frozen_payload,
        metric_count=metric_count,
        input_count=len(inputs) if isinstance(inputs, list) else 0,
    )


@contextmanager
def _registration_lock(project: ResearchProject):
    """Serialize result registration and recovery for one project."""
    lock_path = resolve_project_artifact(project.root, _REGISTRATION_LOCK_PATH)
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _append_registration_failure(
    project: ResearchProject,
    result_path: str,
    error: ValueError,
    *,
    result_sha256: str | None = None,
) -> None:
    try:
        event_project = ResearchProject.open_readonly(project.root)
    except (OSError, TypeError, ValueError):
        event_project = project
    category = str(error)
    if category not in _REGISTRATION_ERROR_CATEGORIES:
        category = "research_result_registration_failed"
    payload: dict[str, object] = {"error_category": category}
    contract_ref = event_project.state.artifacts.get(EXECUTION_CONTRACT_PATH)
    if contract_ref is not None:
        payload.update(
            {
                "contract_path": contract_ref.path,
                "contract_sha256": contract_ref.sha256,
            }
        )
    if result_path == RESEARCH_RESULT_PATH:
        payload["result_path"] = RESEARCH_RESULT_PATH
        if result_sha256 is not None:
            payload["result_sha256"] = result_sha256
    event_log_for(event_project.root).append(
        EvaluationEvent.create(
            "research_result_registration_failed",
            event_project.state.project_id,
            payload,
        )
    )


def _pending_path(project: ResearchProject):
    return resolve_project_artifact(project.root, _REGISTRATION_PENDING_PATH)


def _clear_pending_registration(project: ResearchProject) -> None:
    path = _pending_path(project)
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _load_pending_registration(
    project: ResearchProject,
) -> _PendingResearchResultRegistration | None:
    path = _pending_path(project)
    if not os.path.lexists(path):
        return None
    try:
        raw_bytes = _read_project_file_snapshot(
            project.root, _REGISTRATION_PENDING_PATH
        )
        raw = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        expected_fields = {
            "schema_version",
            "project_id",
            "result_path",
            "result_sha256",
            "result_size",
            "prior_state",
            "target_state",
            "success_event",
        }
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError("invalid pending registration shape")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("invalid pending registration schema")
        project_id = raw["project_id"]
        result_path = raw["result_path"]
        result_sha256 = raw["result_sha256"]
        result_size = raw["result_size"]
        if (
            not isinstance(project_id, str)
            or result_path != RESEARCH_RESULT_PATH
            or not isinstance(result_sha256, str)
            or len(result_sha256) != 64
            or any(character not in "0123456789abcdef" for character in result_sha256)
            or not isinstance(result_size, int)
            or isinstance(result_size, bool)
            or result_size < 0
        ):
            raise ValueError("invalid pending registration identity")
        prior_state = ProjectState.from_dict(raw["prior_state"])
        target_state = ProjectState.from_dict(raw["target_state"])
        success_event = EvaluationEvent.from_dict(raw["success_event"])
        result_ref = target_state.artifacts.get(RESEARCH_RESULT_PATH)
        contract_ref = target_state.artifacts.get(EXECUTION_CONTRACT_PATH)
        if (
            prior_state.project_id != project_id
            or target_state.project_id != project_id
            or success_event.project_id != project_id
            or success_event.type != "research_result_registered"
            or prior_state.current_stage != 12
            or target_state.current_stage != 13
            or 12 not in target_state.completed_stages
            or result_ref is None
            or result_ref.path != result_path
            or result_ref.sha256 != result_sha256
            or result_ref.size != result_size
            or contract_ref is None
            or success_event.payload
            != {
                "contract_path": contract_ref.path,
                "contract_sha256": contract_ref.sha256,
                "result_path": result_path,
                "result_sha256": result_sha256,
                "metric_count": success_event.payload.get("metric_count"),
                "input_count": success_event.payload.get("input_count"),
            }
            or not isinstance(success_event.payload.get("metric_count"), int)
            or isinstance(success_event.payload.get("metric_count"), bool)
            or success_event.payload["metric_count"] < 1
            or not isinstance(success_event.payload.get("input_count"), int)
            or isinstance(success_event.payload.get("input_count"), bool)
            or success_event.payload["input_count"] < 0
        ):
            raise ValueError("invalid pending registration binding")
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise ValueError("research_result_registration_recovery_invalid") from error
    return _PendingResearchResultRegistration(
        project_id=project_id,
        result_path=result_path,
        result_sha256=result_sha256,
        result_size=result_size,
        prior_state=prior_state,
        target_state=target_state,
        success_event=success_event,
    )


def _pending_files_match(
    project: ResearchProject, pending: _PendingResearchResultRegistration
) -> bool:
    for path in (RESEARCH_RESULT_PATH, EXECUTION_CONTRACT_PATH):
        artifact = pending.target_state.artifacts.get(path)
        if artifact is None or artifact.path != path:
            return False
        try:
            payload = _read_project_file_snapshot(project.root, path)
        except (OSError, TypeError, ValueError):
            return False
        if len(payload) != artifact.size or _sha256(payload) != artifact.sha256:
            return False
    return True


def _event_already_present(
    project: ResearchProject, event: EvaluationEvent
) -> bool:
    return any(
        existing.to_dict() == event.to_dict()
        for existing in event_log_for(project.root).read_all()
    )


def _registration_status(
    pending: _PendingResearchResultRegistration,
) -> ResearchResultRegistrationStatus:
    return ResearchResultRegistrationStatus(
        readiness="research_result_registered",
        approval_eligible=False,
        result_path=pending.result_path,
        result_sha256=pending.result_sha256,
        current_stage=pending.target_state.current_stage,
        next_action=pending.target_state.next_action,
    )


def _abort_pending_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    error: ValueError,
) -> None:
    current = ResearchProject.open_readonly(project.root)
    if current.state == pending.target_state:
        current.persist_state(pending.prior_state)
    elif current.state != pending.prior_state:
        raise ValueError("research_result_registration_conflict") from error
    _clear_pending_registration(project)
    _append_registration_failure(
        project,
        pending.result_path,
        error,
        result_sha256=pending.result_sha256,
    )


def _complete_pending_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
) -> ResearchResultRegistrationStatus:
    current = ResearchProject.open_readonly(project.root)
    if current.state == pending.prior_state:
        if not _pending_files_match(current, pending):
            error = ValueError("research_result_file_invalid")
            _abort_pending_registration(current, pending, error)
            raise error
        current = current.persist_state(pending.target_state)
    elif current.state != pending.target_state:
        raise ValueError("research_result_registration_conflict")

    if not _pending_files_match(current, pending):
        error = ValueError("research_result_file_invalid")
        _abort_pending_registration(current, pending, error)
        raise error
    if not _event_already_present(current, pending.success_event):
        event_log_for(current.root).append(pending.success_event)
        if not _event_already_present(current, pending.success_event):
            raise OSError("research result success event was not persisted")
    if not _pending_files_match(current, pending):
        error = ValueError("research_result_file_invalid")
        _abort_pending_registration(current, pending, error)
        raise error
    _clear_pending_registration(current)
    return _registration_status(pending)


def recover_pending_research_result_registration(
    project: ResearchProject,
) -> ResearchResultRegistrationStatus | None:
    """Finish one durable pending registration without duplicating its event."""
    with _registration_lock(project):
        pending = _load_pending_registration(project)
        if pending is None:
            return None
        return _complete_pending_registration(project, pending)


def register_research_result(
    project: ResearchProject, result_path: str
) -> ResearchResultRegistrationStatus:
    """Register one validated research result and complete Stage 12."""
    with _registration_lock(project):
        pending = _load_pending_registration(project)
        if pending is not None:
            return _complete_pending_registration(project, pending)
        try:
            validated = validate_research_result(project, result_path)
            current = _current_project(project)
            try:
                result_bytes = _read_project_file_snapshot(
                    current.root, validated.result_path
                )
            except (OSError, TypeError, ValueError) as error:
                raise ValueError("research_result_file_invalid") from error
            if _sha256(result_bytes) != validated.result_sha256:
                raise ValueError("research_result_file_invalid")
            latest = ResearchProject.open_readonly(current.root)
            if latest.state != current.state:
                raise ValueError("research_result_registration_conflict")
        except ValueError as error:
            _append_registration_failure(project, result_path, error)
            raise

        result_ref = ArtifactRef(
            path=validated.result_path,
            sha256=validated.result_sha256,
            size=len(result_bytes),
        )
        state = latest.state
        target_state = replace(
            state,
            current_stage=13,
            status=StageStatus.READY,
            completed_stages=(
                *tuple(stage for stage in state.completed_stages if stage != 12),
                12,
            ),
            next_action="prepare_stage",
            artifacts={**state.artifacts, validated.result_path: result_ref},
            last_error=None,
        )
        contract_reference = validated.payload["execution_contract"]
        assert isinstance(contract_reference, Mapping)
        success_event = EvaluationEvent.create(
            "research_result_registered",
            state.project_id,
            {
                "contract_path": contract_reference["path"],
                "contract_sha256": contract_reference["sha256"],
                "result_path": validated.result_path,
                "result_sha256": validated.result_sha256,
                "metric_count": validated.metric_count,
                "input_count": validated.input_count,
            },
        )
        pending = _PendingResearchResultRegistration(
            project_id=state.project_id,
            result_path=validated.result_path,
            result_sha256=validated.result_sha256,
            result_size=len(result_bytes),
            prior_state=state,
            target_state=target_state,
            success_event=success_event,
        )
        atomic_write_json(
            _pending_path(project),
            pending.to_dict(),
            prefix="research-result-registration-",
            compact=True,
        )
        return _complete_pending_registration(project, pending)
