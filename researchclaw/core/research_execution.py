"""Explicit, non-executing Stage-12 research execution handoffs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType

from .approval import ApprovalRecord
from .execution_gate import (
    _load_validated_resource_plan,
    _open_project_file_descriptor,
    _project_file_identity,
    _read_project_file_snapshot,
)
from .events import EventLog, EvaluationEvent, MAX_EVENT_RECORD_BYTES, event_log_for
from .execution_environment import inspect_execution_environment
from .experiment_package_contract import (
    SELF_TEST_REPORT_PATH,
    _current_registered_self_test,
    validate_experiment_package_contract,
)
from .models import ArtifactRef, ProjectState, StageStatus
from .paths import resolve_project_artifact
from .persistence import _fsync_directory, atomic_write_json
from .project import ResearchProject
from .resource_planning import RESOURCE_PLAN_PATH, validate_stage_eleven
from .transactions import project_transaction, project_mutation


EXECUTION_CONTRACT_PATH = "experiment/execution_contract.json"
RESEARCH_RESULT_PATH = "experiment/results.json"
_PACKAGE_MANIFEST_PATH = "experiment/package_manifest.json"
_STAGE_TWELVE_APPROVAL_PATH = "approvals/stage-12.json"
_STAGE_TWELVE_ARTIFACT_PATHS = (
    "experiment/design.json",
    _PACKAGE_MANIFEST_PATH,
    "experiment/code/config.json",
    RESOURCE_PLAN_PATH,
    SELF_TEST_REPORT_PATH,
)
_REGISTRATION_LOCK_PATH = "evaluation/events.jsonl"
_REGISTRATION_PENDING_PATH = ".researchclaw/research-result-registration.pending.json"
_MAX_PENDING_REGISTRATION_BYTES = 256 * 1024
MAX_RESEARCH_RESULT_BYTES = 1024 * 1024
MAX_EXECUTION_CONTRACT_BYTES = 256 * 1024
_MAX_APPROVAL_BYTES = 256 * 1024
_MAX_PACKAGE_MANIFEST_BYTES = 1024 * 1024
_CONTRACT_PREPARATION_PENDING_PATH = (
    ".researchclaw/execution-contract-preparation.pending.json"
)
_MAX_CONTRACT_PREPARATION_PENDING_BYTES = 4096
_PENDING_PHASES = frozenset({"committing", "aborting"})
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
        "argv",
        "environment_fingerprint",
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
    argv: tuple[str, ...]
    environment_fingerprint: str
    result_path: str
    contract_path: str
    contract_sha256: str
    bindings: Mapping[str, object]
    inputs: tuple[object, ...]
    result_template: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "argv": list(self.argv),
            "environment_fingerprint": self.environment_fingerprint,
            "result_path": self.result_path,
            "contract_path": self.contract_path,
            "contract_sha256": self.contract_sha256,
            "bindings": _thaw_json(self.bindings),
            "inputs": _thaw_json(self.inputs),
            "result_template": _thaw_json(self.result_template),
        }


@dataclass(frozen=True)
class ValidatedResearchResult:
    result_path: str
    result_sha256: str
    result_size: int
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
    event_log_size: int
    event_log_prefix_sha256: str
    phase: str
    success_written: bool
    event_start_offset: int
    metric_count: int
    input_count: int
    prior_state: ProjectState
    target_state: ProjectState
    success_event: EvaluationEvent
    rollback_event: EvaluationEvent
    failure_event: EvaluationEvent | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 3,
            "project_id": self.project_id,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "result_size": self.result_size,
            "event_log_size": self.event_log_size,
            "event_log_prefix_sha256": self.event_log_prefix_sha256,
            "phase": self.phase,
            "success_written": self.success_written,
            "event_start_offset": self.event_start_offset,
            "metric_count": self.metric_count,
            "input_count": self.input_count,
            "prior_state": self.prior_state.to_dict(),
            "target_state": self.target_state.to_dict(),
            "success_event": self.success_event.to_dict(),
            "rollback_event": self.rollback_event.to_dict(),
            "failure_event": (
                self.failure_event.to_dict() if self.failure_event is not None else None
            ),
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


def _bounded_canonical_json(
    payload: object,
    *,
    maximum_bytes: int,
    error_category: str,
) -> bytes:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    chunks: list[bytes] = []
    size = 0
    try:
        for text_chunk in encoder.iterencode(payload):
            for start in range(0, len(text_chunk), 4096):
                chunk = text_chunk[start : start + 4096].encode("utf-8")
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError(error_category)
                chunks.append(chunk)
    except (TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == error_category:
            raise
        raise ValueError(error_category) from error
    return b"".join(chunks)


def _canonical_event_record(event: EvaluationEvent) -> bytes:
    return EventLog._bounded_record(event)


def _event_identity(event: EvaluationEvent) -> str:
    return _sha256(_canonical_json(event.to_dict()))


def _current_project(project: ResearchProject) -> ResearchProject:
    return ResearchProject.open(project.root)


def _load_strict_stage_twelve_approval(project: ResearchProject) -> ApprovalRecord:
    try:
        payload = _read_project_file_snapshot(
            project.root,
            _STAGE_TWELVE_APPROVAL_PATH,
            max_bytes=_MAX_APPROVAL_BYTES,
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
        not isinstance(raw["schema_version"], int)
        or isinstance(raw["schema_version"], bool)
        or raw["schema_version"] != 1
        or not isinstance(raw["project_id"], str)
        or not isinstance(raw["stage_id"], int)
        or isinstance(raw["stage_id"], bool)
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
    state = project.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("execution_approval_invalid")
    record = _load_strict_stage_twelve_approval(project)
    if (
        record.project_id != state.project_id
        or record.decision != "approve"
        or record.artifact_hashes != _current_stage_twelve_artifact_hashes(project)
    ):
        raise ValueError("execution_approval_invalid")
    return record


def _current_stage_twelve_artifact_hashes(
    project: ResearchProject,
) -> dict[str, str]:
    """Hash approved Stage-12 artifacts only through regular-file snapshots."""
    state = project.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("execution_approval_invalid")
    hashes: dict[str, str] = {}
    for relative_path in _STAGE_TWELVE_ARTIFACT_PATHS:
        artifact = state.artifacts.get(relative_path)
        if artifact is None or artifact.path != relative_path:
            raise ValueError("execution_approval_invalid")
        try:
            identity = _project_file_identity(project.root, relative_path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_approval_invalid") from error
        digest = identity.sha256
        if identity.size != artifact.size or digest != artifact.sha256:
            raise ValueError("execution_approval_invalid")
        hashes[relative_path] = digest
    return hashes


def _load_current_resource_plan(
    project: ResearchProject, *, allow_result: bool = False
) -> dict[str, object]:
    """Reopen and revalidate the persisted Stage-11 resource plan."""
    try:
        _path, raw = _load_validated_resource_plan(project)
        _plan, issues = validate_stage_eleven(project, raw)
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
            identity = _project_file_identity(project.root, path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_prerequisites_changed") from error
        digest = identity.sha256
        if identity.size != declared_size or digest != declared_digest:
            raise ValueError("execution_prerequisites_changed")
        snapshots.append(
            {
                "path": path,
                "size_bytes": identity.size,
                "sha256": digest,
                "license_status": license_status,
            }
        )
    return sorted(snapshots, key=lambda item: str(item["path"]))


def _package_file_bindings(project: ResearchProject) -> list[dict[str, str]]:
    try:
        manifest_bytes = _read_project_file_snapshot(
            project.root,
            _PACKAGE_MANIFEST_PATH,
            max_bytes=_MAX_PACKAGE_MANIFEST_BYTES,
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
            identity = _project_file_identity(project.root, path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_approval_invalid") from error
        actual_digest = identity.sha256
        if actual_digest != expected_digest:
            raise ValueError("execution_approval_invalid")
        bindings.append({"path": path, "sha256": actual_digest})
    return sorted(bindings, key=lambda item: item["path"])


def _contract_id_payload(contract: Mapping[str, object]) -> dict[str, object]:
    return {
        key: contract[key]
        for key in (
            "project_id",
            "argv",
            "environment_fingerprint",
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
    hashes = _current_stage_twelve_artifact_hashes(project)
    plan = _load_current_resource_plan(project, allow_result=allow_result)
    command = plan.get("deferred_command")
    raw_prohibitions = plan.get("prohibitions")
    if (
        not isinstance(command, str)
        or not command
        or not isinstance(raw_prohibitions, Mapping)
    ):
        raise ValueError("execution_prerequisites_changed")
    if hashes.get(RESOURCE_PLAN_PATH) != _sha256(
        _read_project_file_snapshot(
            project.root, RESOURCE_PLAN_PATH, max_bytes=MAX_EXECUTION_CONTRACT_BYTES
        )
    ):
        raise ValueError("execution_approval_invalid")
    try:
        package = validate_experiment_package_contract(project)
    except (OSError, ValueError) as error:
        raise ValueError("execution_approval_invalid") from error
    try:
        environment = inspect_execution_environment(
            Path(sys.executable).resolve(strict=True),
            package.required_distributions,
        )
    except (OSError, ValueError) as error:
        if str(error) == "execution_environment_unavailable":
            raise ValueError("execution_environment_unavailable") from error
        raise ValueError("execution_environment_changed") from error
    try:
        _current_registered_self_test(project, environment=environment)
    except (OSError, ValueError) as error:
        if str(error) in {
            "execution_environment_changed",
            "execution_environment_unavailable",
        }:
            raise ValueError(str(error)) from error
        raise ValueError("execution_approval_invalid") from error
    argv = [environment.interpreter, package.entry_point, *package.execution_argv]

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
        identity = _project_file_identity(project.root, path)
        if identity.sha256 != digest:
            raise ValueError("execution_approval_invalid")
        bindings[name] = {"path": path, "sha256": digest}
    bindings["package_files"] = _package_file_bindings(project)

    prohibitions = dict(raw_prohibitions)
    if not all(
        isinstance(value, bool) and value is False for value in prohibitions.values()
    ):
        raise ValueError("execution_prerequisites_changed")
    prohibitions["researchclaw_managed_execution"] = False
    contract: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "",
        "project_id": project.state.project_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "environment_fingerprint": environment.fingerprint,
        "result_path": RESEARCH_RESULT_PATH,
        "bindings": bindings,
        "inputs": _snapshot_required_inputs(project, plan),
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
        payload = _read_project_file_snapshot(
            project.root,
            EXECUTION_CONTRACT_PATH,
            max_bytes=MAX_EXECUTION_CONTRACT_BYTES,
        )
        existing = _decode_execution_contract(payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("execution_contract_invalid") from error
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
            "execution_contract_stale"
            if stale_category
            else "execution_contract_invalid"
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
    artifact = project.state.artifacts.get(EXECUTION_CONTRACT_PATH)
    if artifact is None:
        journal = _load_contract_preparation_journal(project)
        if journal != {
            "schema_version": 1,
            "project_id": project.state.project_id,
            "contract_id": existing["contract_id"],
            "contract_sha256": _sha256(payload),
            "contract_size": len(payload),
        }:
            raise ValueError("execution_contract_invalid")
    elif (
        artifact.path != EXECUTION_CONTRACT_PATH
        or artifact.size != len(payload)
        or artifact.sha256 != _sha256(payload)
    ):
        raise ValueError("execution_contract_invalid")
    return payload


def _contract_preparation_path(project: ResearchProject) -> Path:
    return resolve_project_artifact(
        project.root,
        _CONTRACT_PREPARATION_PENDING_PATH,
    )


def _load_contract_preparation_journal(
    project: ResearchProject,
) -> dict[str, object] | None:
    path = _contract_preparation_path(project)
    if not os.path.lexists(path):
        return None
    try:
        payload = _read_project_file_snapshot(
            project.root,
            _CONTRACT_PREPARATION_PENDING_PATH,
            max_bytes=_MAX_CONTRACT_PREPARATION_PENDING_BYTES,
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
        raise ValueError("execution_contract_invalid") from error
    fields = {
        "schema_version",
        "project_id",
        "contract_id",
        "contract_sha256",
        "contract_size",
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != fields
        or raw.get("schema_version") != 1
        or not isinstance(raw.get("project_id"), str)
        or not isinstance(raw.get("contract_id"), str)
        or not isinstance(raw.get("contract_sha256"), str)
        or len(raw["contract_sha256"]) != 64
        or not isinstance(raw.get("contract_size"), int)
        or isinstance(raw.get("contract_size"), bool)
        or raw["contract_size"] < 0
    ):
        raise ValueError("execution_contract_invalid")
    return raw


def _persist_contract_preparation_journal(
    project: ResearchProject,
    payload: bytes,
    contract_id: object,
) -> None:
    journal: dict[str, object] = {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "contract_id": contract_id,
        "contract_sha256": _sha256(payload),
        "contract_size": len(payload),
    }
    _bounded_canonical_json(
        journal,
        maximum_bytes=_MAX_CONTRACT_PREPARATION_PENDING_BYTES,
        error_category="execution_contract_invalid",
    )
    atomic_write_json(
        _contract_preparation_path(project),
        journal,
        prefix="execution-contract-preparation-",
        compact=True,
    )


def _clear_contract_preparation_journal(project: ResearchProject) -> None:
    path = _contract_preparation_path(project)
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _reject_duplicate_keys(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError("non-finite JSON constant")


def _decode_research_result(payload: bytes) -> object:
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def _decode_execution_contract(payload: bytes) -> object:
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
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
        config_bytes = _read_project_file_snapshot(
            project.root, config_path, max_bytes=MAX_EXECUTION_CONTRACT_BYTES
        )
        config = json.loads(
            config_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
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
    if (
        not isinstance(split_summary, dict)
        or set(split_summary) != expected_split_fields
    ):
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


@project_mutation
def prepare_research_execution(project: ResearchProject) -> ExecutionPreparationStatus:
    """Write an approved immutable handoff without importing or running project code."""
    current = _current_project(project)
    _load_current_stage_twelve_approval(current)
    registration_recovery = (
        current.state.next_action == "prepare_run"
        and isinstance(current.state.last_error, dict)
        and current.state.last_error.get("retry_state")
        == "stage_twelve_registration_recovery"
    )
    contract = _build_execution_contract(
        current,
        allow_result=registration_recovery,
    )
    try:
        existing = _existing_current_contract(current, contract)
    except ValueError as error:
        if (
            not registration_recovery
            or str(error)
            not in {"execution_contract_invalid", "execution_contract_stale"}
            or current.state.artifacts.get(EXECUTION_CONTRACT_PATH) is None
        ):
            raise
        existing = None
    if existing is None:
        candidate_bytes = _bounded_canonical_json(
            contract,
            maximum_bytes=MAX_EXECUTION_CONTRACT_BYTES,
            error_category="execution_contract_invalid",
        )
        _persist_contract_preparation_journal(
            current,
            candidate_bytes,
            contract.get("contract_id"),
        )
        path = resolve_project_artifact(current.root, EXECUTION_CONTRACT_PATH)
        atomic_write_json(
            path,
            contract,
            prefix="execution-contract-",
            compact=True,
        )
        try:
            existing = _read_project_file_snapshot(
                current.root,
                EXECUTION_CONTRACT_PATH,
                max_bytes=MAX_EXECUTION_CONTRACT_BYTES,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("execution_contract_invalid") from error
    _record_contract_artifact(_current_project(current), existing)
    _clear_contract_preparation_journal(current)
    stored_contract = _decode_execution_contract(existing)
    bindings = _freeze_json(stored_contract["bindings"])
    inputs = _freeze_json(stored_contract["inputs"])
    result_template = _freeze_json(stored_contract["result_template"])
    assert isinstance(bindings, Mapping)
    assert isinstance(inputs, tuple)
    assert isinstance(result_template, Mapping)
    return ExecutionPreparationStatus(
        readiness="ready_for_explicit_execution",
        approval_eligible=False,
        argv=tuple(contract["argv"]),
        environment_fingerprint=str(contract["environment_fingerprint"]),
        result_path=RESEARCH_RESULT_PATH,
        contract_path=EXECUTION_CONTRACT_PATH,
        contract_sha256=_sha256(existing),
        bindings=bindings,
        inputs=inputs,
        result_template=result_template,
    )


def validate_research_result(
    project: ResearchProject, result_path: str
) -> ValidatedResearchResult:
    """Return a validated result snapshot without mutating project state or events."""
    current = ResearchProject.open_readonly(project.root)
    return _validate_research_result_against_stage_twelve_state(
        current.root,
        current.state,
        result_path,
    )


def _validate_research_result_against_stage_twelve_state(
    root: Path,
    stage_twelve_state: ProjectState,
    result_path: str,
) -> ValidatedResearchResult:
    """Strict side-effect-free validator shared by registration and recovery."""
    if result_path == "experiment/dev_results.json":
        raise ValueError("development_result_not_registerable")
    if result_path != RESEARCH_RESULT_PATH:
        raise ValueError("research_result_file_invalid")
    current = ResearchProject(
        root=Path(root).resolve(strict=True), state=stage_twelve_state
    )
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
        result_bytes = _read_project_file_snapshot(
            current.root,
            result_path,
            max_bytes=MAX_RESEARCH_RESULT_BYTES,
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("research_result_file_invalid") from error
    try:
        payload = _decode_research_result(result_bytes)
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
    if (
        payload["development_only"] is not False
        or payload["evidence_eligible"] is not True
    ):
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
        result_size=len(result_bytes),
        payload=frozen_payload,
        metric_count=metric_count,
        input_count=len(inputs) if isinstance(inputs, list) else 0,
    )


def _registration_lock(project: ResearchProject):
    """Serialize result registration and recovery for one project."""
    return project_transaction(project.root, allow_pending=True)


def _registration_failure_event(
    project: ResearchProject,
    result_path: str,
    error: ValueError,
    *,
    result_sha256: str | None = None,
) -> EvaluationEvent:
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
    return EvaluationEvent.create(
        "research_result_registration_failed",
        event_project.state.project_id,
        payload,
    )


def _append_registration_failure(
    project: ResearchProject,
    result_path: str,
    error: ValueError,
    *,
    result_sha256: str | None = None,
) -> None:
    event = _registration_failure_event(
        project,
        result_path,
        error,
        result_sha256=result_sha256,
    )
    try:
        event_log_size, _event_log_sha256 = _read_complete_registration_event_log(
            project
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as log_error:
        raise ValueError("research_result_registration_recovery_invalid") from log_error
    event_log_for(project.root).append_locked(
        event,
        expected_offset=event_log_size,
    )


def _pending_path(project: ResearchProject):
    return resolve_project_artifact(project.root, _REGISTRATION_PENDING_PATH)


def _clear_pending_registration(project: ResearchProject) -> None:
    path = _pending_path(project)
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _read_bounded_pending_registration(project: ResearchProject) -> bytes:
    """Read the regular pending file only when it fits the 256-KiB protocol cap."""
    path = _pending_path(project)
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > _MAX_PENDING_REGISTRATION_BYTES
        ):
            raise ValueError("pending registration file is invalid")
        chunks: list[bytes] = []
        remaining = _MAX_PENDING_REGISTRATION_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > _MAX_PENDING_REGISTRATION_BYTES:
            raise ValueError("pending registration file is too large")
        return payload
    finally:
        os.close(descriptor)


_PROJECT_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "project_id",
        "topic",
        "profile",
        "current_stage",
        "status",
        "completed_stages",
        "next_action",
        "execution_policy",
        "artifacts",
        "retry_counts",
        "last_error",
        "stage_10_snapshot",
    }
)
_EVENT_FIELDS = frozenset(
    {"schema_version", "timestamp", "type", "project_id", "payload"}
)


def _require_closed_pending_state(raw: object) -> None:
    if not isinstance(raw, dict) or set(raw) != _PROJECT_STATE_FIELDS:
        raise ValueError("pending state must be a closed object")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict) or any(
        not isinstance(reference, dict) or set(reference) != {"path", "sha256", "size"}
        for reference in artifacts.values()
    ):
        raise ValueError("pending artifacts must contain closed references")
    snapshot = raw.get("stage_10_snapshot")
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"status", "entries"}
        or not isinstance(snapshot.get("entries"), list)
        or any(
            not isinstance(entry, dict) or set(entry) != {"path", "kind", "sha256"}
            for entry in snapshot["entries"]
        )
    ):
        raise ValueError("pending stage-10 snapshot must be closed")
    last_error = raw.get("last_error")
    if last_error is None:
        return
    if not isinstance(last_error, dict) or set(last_error) != {
        "error_class",
        "stage_id",
        "attempt_number",
        "issues",
        "artifact_hashes",
        "recommended_action",
        "retry_state",
    }:
        raise ValueError("pending last_error must be closed")
    issues = last_error.get("issues")
    if not isinstance(issues, list) or any(
        not isinstance(issue, dict) or set(issue) != {"code", "path", "message"}
        for issue in issues
    ):
        raise ValueError("pending last_error issues must be closed")


def _require_closed_pending_event(raw: object) -> None:
    if (
        not isinstance(raw, dict)
        or set(raw) != _EVENT_FIELDS
        or not isinstance(raw.get("payload"), dict)
    ):
        raise ValueError("pending event must be a closed object")


def _load_pending_registration(
    project: ResearchProject,
) -> _PendingResearchResultRegistration | None:
    path = _pending_path(project)
    if not os.path.lexists(path):
        return None
    try:
        raw_bytes = _read_bounded_pending_registration(project)
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
            "event_log_size",
            "event_log_prefix_sha256",
            "phase",
            "success_written",
            "event_start_offset",
            "metric_count",
            "input_count",
            "prior_state",
            "target_state",
            "success_event",
            "rollback_event",
            "failure_event",
        }
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError("invalid pending registration shape")
        if (
            not isinstance(raw["schema_version"], int)
            or isinstance(raw["schema_version"], bool)
            or raw["schema_version"] != 3
        ):
            raise ValueError("invalid pending registration schema")
        project_id = raw["project_id"]
        result_path = raw["result_path"]
        result_sha256 = raw["result_sha256"]
        result_size = raw["result_size"]
        event_log_size = raw["event_log_size"]
        event_log_prefix_sha256 = raw["event_log_prefix_sha256"]
        phase = raw["phase"]
        success_written = raw["success_written"]
        event_start_offset = raw["event_start_offset"]
        metric_count = raw["metric_count"]
        input_count = raw["input_count"]
        if (
            not isinstance(project_id, str)
            or result_path != RESEARCH_RESULT_PATH
            or not isinstance(result_sha256, str)
            or len(result_sha256) != 64
            or any(character not in "0123456789abcdef" for character in result_sha256)
            or not isinstance(result_size, int)
            or isinstance(result_size, bool)
            or result_size < 0
            or not isinstance(event_log_size, int)
            or isinstance(event_log_size, bool)
            or event_log_size < 0
            or not isinstance(event_log_prefix_sha256, str)
            or len(event_log_prefix_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in event_log_prefix_sha256
            )
            or phase not in _PENDING_PHASES
            or not isinstance(success_written, bool)
            or not isinstance(event_start_offset, int)
            or isinstance(event_start_offset, bool)
            or event_start_offset < 0
            or not isinstance(metric_count, int)
            or isinstance(metric_count, bool)
            or metric_count < 1
            or not isinstance(input_count, int)
            or isinstance(input_count, bool)
            or input_count < 0
        ):
            raise ValueError("invalid pending registration identity")
        _require_closed_pending_state(raw["prior_state"])
        _require_closed_pending_state(raw["target_state"])
        _require_closed_pending_event(raw["success_event"])
        _require_closed_pending_event(raw["rollback_event"])
        if raw["failure_event"] is not None:
            _require_closed_pending_event(raw["failure_event"])
        prior_state = ProjectState.from_dict(raw["prior_state"])
        target_state = ProjectState.from_dict(raw["target_state"])
        success_event = EvaluationEvent.from_dict(raw["success_event"])
        rollback_event = EvaluationEvent.from_dict(raw["rollback_event"])
        failure_event = (
            EvaluationEvent.from_dict(raw["failure_event"])
            if raw["failure_event"] is not None
            else None
        )
        result_ref = target_state.artifacts.get(RESEARCH_RESULT_PATH)
        contract_ref = prior_state.artifacts.get(EXECUTION_CONTRACT_PATH)
        expected_target_state = replace(
            prior_state,
            current_stage=13,
            status=StageStatus.READY,
            completed_stages=(
                *tuple(stage for stage in prior_state.completed_stages if stage != 12),
                12,
            ),
            next_action="prepare_stage",
            artifacts={**prior_state.artifacts, result_path: result_ref}
            if result_ref is not None
            else prior_state.artifacts,
            last_error=None,
        )
        expected_success_payload = (
            {
                "contract_path": contract_ref.path,
                "contract_sha256": contract_ref.sha256,
                "result_path": result_path,
                "result_sha256": result_sha256,
                "metric_count": metric_count,
                "input_count": input_count,
            }
            if contract_ref is not None
            else None
        )
        expected_rollback_payload = (
            {
                "contract_path": expected_success_payload["contract_path"],
                "contract_sha256": expected_success_payload["contract_sha256"],
                "result_path": result_path,
                "result_sha256": result_sha256,
                "registration_event_sha256": _event_identity(success_event),
            }
            if expected_success_payload is not None
            else None
        )
        expected_failure_binding = (
            {
                "contract_path": contract_ref.path,
                "contract_sha256": contract_ref.sha256,
                "result_path": result_path,
                "result_sha256": result_sha256,
            }
            if contract_ref is not None
            else None
        )
        success_record_size = len(_canonical_event_record(success_event))
        if (
            prior_state.project_id != project_id
            or target_state.project_id != project_id
            or success_event.project_id != project_id
            or success_event.type != "research_result_registered"
            or rollback_event.project_id != project_id
            or rollback_event.type != "research_result_registration_rolled_back"
            or prior_state.current_stage != 12
            or 11 not in prior_state.completed_stages
            or 12 in prior_state.completed_stages
            or result_ref is None
            or result_ref.path != result_path
            or result_ref.sha256 != result_sha256
            or result_ref.size != result_size
            or contract_ref is None
            or target_state != expected_target_state
            or success_event.payload != expected_success_payload
            or rollback_event.payload != expected_rollback_payload
            or (phase == "committing" and success_written)
            or (phase == "committing" and event_start_offset != event_log_size)
            or (phase == "committing" and failure_event is not None)
            or (
                phase == "aborting"
                and event_start_offset
                != event_log_size + (success_record_size if success_written else 0)
            )
            or (phase == "aborting" and failure_event is None)
            or (
                failure_event is not None
                and (
                    failure_event.project_id != project_id
                    or failure_event.type != "research_result_registration_failed"
                    or failure_event.payload.get("error_category")
                    not in _REGISTRATION_ERROR_CATEGORIES
                    or {
                        key: value
                        for key, value in failure_event.payload.items()
                        if key != "error_category"
                    }
                    != expected_failure_binding
                )
            )
        ):
            raise ValueError("invalid pending registration binding")
        pending_for_counts = _PendingResearchResultRegistration(
            project_id=project_id,
            result_path=result_path,
            result_sha256=result_sha256,
            result_size=result_size,
            event_log_size=event_log_size,
            event_log_prefix_sha256=event_log_prefix_sha256,
            phase=phase,
            success_written=success_written,
            event_start_offset=event_start_offset,
            metric_count=metric_count,
            input_count=input_count,
            prior_state=prior_state,
            target_state=target_state,
            success_event=success_event,
            rollback_event=rollback_event,
            failure_event=failure_event,
        )
        if _pending_files_match(project, pending_for_counts):
            result_bytes = _read_project_file_snapshot(
                project.root,
                result_path,
                max_bytes=MAX_RESEARCH_RESULT_BYTES,
            )
            contract_bytes = _read_project_file_snapshot(
                project.root,
                EXECUTION_CONTRACT_PATH,
                max_bytes=MAX_EXECUTION_CONTRACT_BYTES,
            )
            result_payload = _decode_research_result(result_bytes)
            contract_payload = _decode_execution_contract(contract_bytes)
            recomputed_metric_count = _validate_result_metrics(
                result_payload.get("metrics")
                if isinstance(result_payload, dict)
                else None
            )
            contract_inputs = (
                contract_payload.get("inputs")
                if isinstance(contract_payload, dict)
                and set(contract_payload) == _CONTRACT_FIELDS
                else None
            )
            if (
                not isinstance(contract_inputs, list)
                or _canonical_json(contract_payload) != contract_bytes
                or contract_payload.get("project_id") != project_id
                or contract_payload.get("result_path") != result_path
                or contract_payload.get("contract_id")
                != _sha256(_canonical_json(_contract_id_payload(contract_payload)))
                or metric_count != recomputed_metric_count
                or input_count != len(contract_inputs)
            ):
                raise ValueError("pending registration counts are invalid")
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
        event_log_size=event_log_size,
        event_log_prefix_sha256=event_log_prefix_sha256,
        phase=phase,
        success_written=success_written,
        event_start_offset=event_start_offset,
        metric_count=metric_count,
        input_count=input_count,
        prior_state=prior_state,
        target_state=target_state,
        success_event=success_event,
        rollback_event=rollback_event,
        failure_event=failure_event,
    )


def _pending_files_match(
    project: ResearchProject, pending: _PendingResearchResultRegistration
) -> bool:
    for path in (RESEARCH_RESULT_PATH, EXECUTION_CONTRACT_PATH):
        artifact = pending.target_state.artifacts.get(path)
        if artifact is None or artifact.path != path:
            return False
        try:
            identity = _project_file_identity(project.root, path)
        except (OSError, TypeError, ValueError):
            return False
        if identity.size != artifact.size or identity.sha256 != artifact.sha256:
            return False
    return True


def _parse_event_record(line: bytes) -> EvaluationEvent:
    if not line or not line.endswith(b"\n"):
        raise ValueError("incomplete event record")
    raw = json.loads(
        line[:-1].decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )
    return EvaluationEvent.from_dict(raw)


def _read_complete_registration_event_log(
    project: ResearchProject,
) -> tuple[int, str]:
    for _event in event_log_for(project.root).iter_events():
        pass
    identity = _project_file_identity(project.root, _REGISTRATION_LOCK_PATH)
    return identity.size, identity.sha256


def _event_prefix_tail(
    project: ResearchProject,
    *,
    prefix_size: int,
    prefix_sha256: str,
    maximum_tail_bytes: int,
) -> bytes:
    """Validate a streamed JSONL prefix and retain only its bounded tail."""
    descriptor, _relative_path = _open_project_file_descriptor(
        project.root, _REGISTRATION_LOCK_PATH
    )
    try:
        total_size = os.fstat(descriptor).st_size
        if (
            prefix_size < 0
            or total_size < prefix_size
            or total_size - prefix_size > maximum_tail_bytes
        ):
            raise ValueError("research_result_registration_recovery_invalid")
        digest = hashlib.sha256()
        remaining = prefix_size
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while remaining:
                line = handle.readline(min(MAX_EVENT_RECORD_BYTES + 1, remaining + 1))
                if (
                    not line
                    or len(line) > MAX_EVENT_RECORD_BYTES
                    or len(line) > remaining
                ):
                    raise ValueError("research_result_registration_recovery_invalid")
                _parse_event_record(line)
                digest.update(line)
                remaining -= len(line)
            if digest.hexdigest() != prefix_sha256:
                raise ValueError("research_result_registration_recovery_invalid")
            tail = handle.read(maximum_tail_bytes + 1)
            if len(tail) > maximum_tail_bytes or handle.read(1):
                raise ValueError("research_result_registration_recovery_invalid")
            return tail
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        if isinstance(error, ValueError) and str(error) == (
            "research_result_registration_recovery_invalid"
        ):
            raise
        raise ValueError("research_result_registration_recovery_invalid") from error
    finally:
        os.close(descriptor)


def _truncate_registration_event_log(project: ResearchProject, size: int) -> None:
    path = resolve_project_artifact(project.root, _REGISTRATION_LOCK_PATH)
    descriptor = os.open(
        path,
        os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.ftruncate(descriptor, size)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _pending_event_tail(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
) -> bytes:
    return _event_prefix_tail(
        project,
        prefix_size=pending.event_log_size,
        prefix_sha256=pending.event_log_prefix_sha256,
        maximum_tail_bytes=3 * MAX_EVENT_RECORD_BYTES,
    )


def _require_owned_event_fragment(
    pending: _PendingResearchResultRegistration,
    *,
    fragment: bytes,
    event: EvaluationEvent,
) -> None:
    record = _canonical_event_record(event)
    identity_markers = (
        pending.result_sha256.encode("ascii"),
        str(pending.success_event.payload["contract_sha256"]).encode("ascii"),
    )
    if (
        not fragment
        or not record.startswith(fragment)
        or not any(marker in fragment for marker in identity_markers)
    ):
        raise ValueError("research_result_registration_recovery_invalid")


def _repair_owned_event_fragment(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    *,
    offset: int,
    fragment: bytes,
    event: EvaluationEvent,
) -> None:
    _require_owned_event_fragment(
        pending,
        fragment=fragment,
        event=event,
    )
    _truncate_registration_event_log(project, offset)


def _committing_success_written(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    *,
    repair_partial: bool,
) -> bool:
    if pending.phase != "committing":
        raise ValueError("research_result_registration_recovery_invalid")
    tail = _pending_event_tail(project, pending)
    if pending.event_start_offset != pending.event_log_size:
        raise ValueError("research_result_registration_recovery_invalid")
    record = _canonical_event_record(pending.success_event)
    if tail == record:
        return True
    if not tail:
        return False
    _require_owned_event_fragment(
        pending,
        fragment=tail,
        event=pending.success_event,
    )
    if repair_partial:
        _truncate_registration_event_log(project, pending.event_start_offset)
    return False


def _append_pending_event(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    event: EvaluationEvent,
    *,
    expected_offset: int,
) -> None:
    event_log_for(project.root).append_locked(
        event,
        expected_offset=expected_offset,
    )
    record = _canonical_event_record(event)
    descriptor, _relative_path = _open_project_file_descriptor(
        project.root, _REGISTRATION_LOCK_PATH
    )
    try:
        if os.fstat(descriptor).st_size != expected_offset + len(record):
            raise OSError("research result transaction event was not persisted")
        os.lseek(descriptor, expected_offset, os.SEEK_SET)
        persisted = os.read(descriptor, len(record) + 1)
    finally:
        os.close(descriptor)
    if persisted != record:
        raise OSError("research result transaction event was not persisted")


def _persist_pending_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
) -> None:
    _bounded_canonical_json(
        pending.to_dict(),
        maximum_bytes=_MAX_PENDING_REGISTRATION_BYTES,
        error_category="research_result_registration_recovery_invalid",
    )
    atomic_write_json(
        _pending_path(project),
        pending.to_dict(),
        prefix="research-result-registration-",
        compact=True,
    )


def _begin_aborting_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    error: ValueError,
) -> _PendingResearchResultRegistration:
    if pending.phase == "aborting":
        return pending
    success_written = _committing_success_written(
        project, pending, repair_partial=False
    )
    failure_event = _registration_failure_event(
        project,
        pending.result_path,
        error,
        result_sha256=pending.result_sha256,
    )
    aborting = replace(
        pending,
        phase="aborting",
        success_written=success_written,
        event_start_offset=pending.event_log_size
        + (
            len(_canonical_event_record(pending.success_event))
            if success_written
            else 0
        ),
        failure_event=failure_event,
    )
    _persist_pending_registration(project, aborting)
    return aborting


def _ensure_aborting_events(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
) -> None:
    if pending.phase != "aborting" or pending.failure_event is None:
        raise ValueError("research_result_registration_recovery_invalid")
    tail = _pending_event_tail(project, pending)
    expected_prefix = pending.event_log_size
    if pending.success_written:
        success_record = _canonical_event_record(pending.success_event)
        success_offset = expected_prefix - pending.event_log_size
        if (
            tail[success_offset : success_offset + len(success_record)]
            != success_record
        ):
            raise ValueError("research_result_registration_recovery_invalid")
        expected_prefix += len(success_record)
    if expected_prefix != pending.event_start_offset:
        raise ValueError("research_result_registration_recovery_invalid")

    if not pending.success_written:
        event_tail = tail[pending.event_start_offset - pending.event_log_size :]
        success_record = _canonical_event_record(pending.success_event)
        if (
            event_tail
            and len(event_tail) < len(success_record)
            and success_record.startswith(event_tail)
        ):
            _repair_owned_event_fragment(
                project,
                pending,
                offset=pending.event_start_offset,
                fragment=event_tail,
                event=pending.success_event,
            )

    events = (
        (pending.rollback_event, pending.failure_event)
        if pending.success_written
        else (pending.failure_event,)
    )
    offset = pending.event_start_offset
    for event in events:
        record = _canonical_event_record(event)
        current_tail = _pending_event_tail(project, pending)
        fragment = current_tail[offset - pending.event_log_size :]
        if fragment.startswith(record):
            offset += len(record)
            continue
        if fragment:
            _repair_owned_event_fragment(
                project,
                pending,
                offset=offset,
                fragment=fragment,
                event=event,
            )
        _append_pending_event(
            project,
            pending,
            event,
            expected_offset=offset,
        )
        offset += len(record)
    final_identity = _project_file_identity(project.root, _REGISTRATION_LOCK_PATH)
    if final_identity.size != offset:
        raise ValueError("research_result_registration_recovery_invalid")


def effective_research_result_registration_events(
    project: ResearchProject,
) -> tuple[EvaluationEvent, ...]:
    """Return completed registrations not neutralized by a rollback event."""
    events = event_log_for(project.root).read_all()
    rolled_back = {
        identity
        for event in events
        if event.type == "research_result_registration_rolled_back"
        and isinstance(identity := event.payload.get("registration_event_sha256"), str)
    }
    return tuple(
        event
        for event in events
        if event.type == "research_result_registered"
        and _event_identity(event) not in rolled_back
    )


def research_result_registration_is_grounded(
    project: ResearchProject,
    *,
    contract_path: str,
    contract_sha256: str,
    result_path: str,
    result_sha256: str,
    metric_count: int,
    input_count: int,
) -> bool:
    """Stream the log twice to ground one result with constant memory."""
    expected_success = {
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "result_path": result_path,
        "result_sha256": result_sha256,
        "metric_count": metric_count,
        "input_count": input_count,
    }
    latest_identity: str | None = None
    log = event_log_for(project.root)
    for event in log.iter_events():
        if (
            event.project_id == project.state.project_id
            and event.type == "research_result_registered"
            and event.payload == expected_success
        ):
            latest_identity = _event_identity(event)
    if latest_identity is None:
        return False

    expected_rollback = {
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "result_path": result_path,
        "result_sha256": result_sha256,
        "registration_event_sha256": latest_identity,
    }
    return not any(
        event.project_id == project.state.project_id
        and event.type == "research_result_registration_rolled_back"
        and event.payload == expected_rollback
        for event in log.iter_events()
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
    pending = _begin_aborting_registration(project, pending, error)
    _finish_aborting_registration(project, pending)


def _finish_aborting_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
) -> None:
    if pending.phase != "aborting":
        raise ValueError("research_result_registration_recovery_invalid")
    current = ResearchProject.open_readonly(project.root)
    if current.state == pending.target_state:
        current = current.persist_state(pending.prior_state)
    elif current.state != pending.prior_state:
        raise ValueError("research_result_registration_conflict")
    _ensure_aborting_events(current, pending)
    _clear_pending_registration(current)


def _complete_pending_registration(
    project: ResearchProject,
    pending: _PendingResearchResultRegistration,
    *,
    suppress_validation_failure: bool = False,
) -> ResearchResultRegistrationStatus | None:
    if pending.phase != "committing":
        raise ValueError("research_result_registration_recovery_invalid")
    current = ResearchProject.open_readonly(project.root)
    try:
        validated = _validate_research_result_against_stage_twelve_state(
            current.root,
            pending.prior_state,
            pending.result_path,
        )
        if (
            validated.result_sha256 != pending.result_sha256
            or validated.result_size != pending.result_size
            or validated.metric_count != pending.metric_count
            or validated.input_count != pending.input_count
        ):
            raise ValueError("research_result_registration_recovery_invalid")
    except ValueError as error:
        category = str(error)
        normalized = (
            error
            if category in _REGISTRATION_ERROR_CATEGORIES
            else ValueError("research_result_registration_recovery_invalid")
        )
        _abort_pending_registration(current, pending, normalized)
        if suppress_validation_failure:
            return None
        raise normalized
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
    if not _committing_success_written(current, pending, repair_partial=True):
        _append_pending_event(
            current,
            pending,
            pending.success_event,
            expected_offset=pending.event_start_offset,
        )
    if not _pending_files_match(current, pending):
        error = ValueError("research_result_file_invalid")
        _abort_pending_registration(current, pending, error)
        raise error
    _clear_pending_registration(current)
    return _registration_status(pending)


def recover_pending_research_result_registration(
    project: ResearchProject,
) -> object | None:
    """Finish one durable pending registration without duplicating its event."""
    from .evidence_registration import recover_pending_evidence_registration

    recovered = recover_pending_evidence_registration(project)
    if recovered is not None:
        return recovered
    with _registration_lock(project):
        return _recover_pending_registration_locked(project)


def _recover_pending_registration_locked(
    project: ResearchProject,
    *,
    suppress_validation_failure: bool = False,
) -> object | None:
    """Recover a pending registration while the caller owns the project lock."""
    from .evidence_registration import (
        _load_pending as _load_evidence_pending,
        _recover_locked as _recover_evidence_locked,
    )

    current = ResearchProject.open_readonly(project.root)
    evidence_pending = _load_evidence_pending(current)
    if evidence_pending is not None:
        return _recover_evidence_locked(current, evidence_pending)
    pending = _load_pending_registration(project)
    if pending is None:
        return None
    if pending.phase == "aborting":
        _finish_aborting_registration(project, pending)
        return None
    return _complete_pending_registration(
        project,
        pending,
        suppress_validation_failure=suppress_validation_failure,
    )


def register_research_result(project: ResearchProject, result_path: str) -> object:
    """Register one validated research result and complete Stage 12."""
    from .evidence_registration import (
        _validated_event_log_offset,
        recover_pending_evidence_registration,
        registered_evidence_status,
        register_immutable_research_evidence,
    )

    # Finish or reject journals created by releases before immutable evidence.
    # They are never silently migrated into the new manifest format.
    if os.path.lexists(_pending_path(project)):
        with _registration_lock(project):
            pending = _load_pending_registration(project)
            if pending is None:
                raise ValueError("research_result_registration_recovery_invalid")
            if pending.phase == "aborting":
                category = (
                    pending.failure_event.payload["error_category"]
                    if pending.failure_event is not None
                    else "research_result_registration_recovery_invalid"
                )
                _finish_aborting_registration(project, pending)
                raise ValueError(str(category))
            return _complete_pending_registration(project, pending)
    try:
        with project_transaction(project.root, allow_pending=True):
            current = _current_project(project)
            recovered = recover_pending_evidence_registration(current)
            if recovered is not None:
                return recovered
            current = _current_project(project)
            registered = registered_evidence_status(current)
            if registered is not None:
                return registered
            _validated_event_log_offset(current)
            validated = validate_research_result(current, result_path)
            return register_immutable_research_evidence(current, validated)
    except ValueError as error:
        from .evidence_registration import EVIDENCE_PENDING_PATH

        if not os.path.lexists(project.root / EVIDENCE_PENDING_PATH):
            try:
                _append_registration_failure(project, result_path, error)
            except ValueError:
                pass
        raise


def _register_mutable_research_result_legacy(
    project: ResearchProject, result_path: str
) -> ResearchResultRegistrationStatus:
    """Retained parser/recovery implementation for legacy pending journals only."""
    with _registration_lock(project):
        pending = _load_pending_registration(project)
        if pending is not None:
            if pending.phase == "aborting":
                category = (
                    pending.failure_event.payload["error_category"]
                    if pending.failure_event is not None
                    else "research_result_registration_recovery_invalid"
                )
                _finish_aborting_registration(project, pending)
                raise ValueError(str(category))
            return _complete_pending_registration(project, pending)
        try:
            current = _current_project(project)
            validated = validate_research_result(current, result_path)
            try:
                result_identity = _project_file_identity(
                    current.root, validated.result_path
                )
            except (OSError, TypeError, ValueError) as error:
                raise ValueError("research_result_file_invalid") from error
            if (
                result_identity.sha256 != validated.result_sha256
                or result_identity.size != validated.result_size
            ):
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
            size=validated.result_size,
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
        rollback_event = EvaluationEvent.create(
            "research_result_registration_rolled_back",
            state.project_id,
            {
                "contract_path": contract_reference["path"],
                "contract_sha256": contract_reference["sha256"],
                "result_path": validated.result_path,
                "result_sha256": validated.result_sha256,
                "registration_event_sha256": _event_identity(success_event),
            },
        )
        try:
            (
                event_log_size,
                event_log_prefix_sha256,
            ) = _read_complete_registration_event_log(latest)
        except (
            OSError,
            UnicodeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            RecursionError,
        ) as error:
            invalid = ValueError("research_result_registration_recovery_invalid")
            _append_registration_failure(project, result_path, invalid)
            raise invalid from error
        pending = _PendingResearchResultRegistration(
            project_id=state.project_id,
            result_path=validated.result_path,
            result_sha256=validated.result_sha256,
            result_size=validated.result_size,
            event_log_size=event_log_size,
            event_log_prefix_sha256=event_log_prefix_sha256,
            phase="committing",
            success_written=False,
            event_start_offset=event_log_size,
            metric_count=validated.metric_count,
            input_count=validated.input_count,
            prior_state=state,
            target_state=target_state,
            success_event=success_event,
            rollback_event=rollback_event,
            failure_event=None,
        )
        _persist_pending_registration(project, pending)
        return _complete_pending_registration(project, pending)
