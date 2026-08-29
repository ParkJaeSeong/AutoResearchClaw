"""Explicit, non-executing Stage-12 research execution handoffs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json

from .approval import ApprovalRecord, approval_matches_state, load_approval_record
from .execution_gate import (
    _load_validated_resource_plan,
    _read_project_file_snapshot,
    stage_twelve_artifact_hashes,
)
from .models import ArtifactRef
from .paths import resolve_project_artifact
from .persistence import atomic_write_json
from .project import ResearchProject
from .resource_planning import RESOURCE_PLAN_PATH, validate_stage_eleven


EXECUTION_CONTRACT_PATH = "experiment/execution_contract.json"
RESEARCH_RESULT_PATH = "experiment/results.json"
_PACKAGE_MANIFEST_PATH = "experiment/package_manifest.json"
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


def _load_current_stage_twelve_approval(project: ResearchProject) -> ApprovalRecord:
    """Require a current, explicit Stage-12 approval."""
    current = _current_project(project)
    state = current.state
    if state.current_stage != 12 or 11 not in state.completed_stages:
        raise ValueError("execution_approval_invalid")
    record = load_approval_record(current.root, 12)
    if (
        record is None
        or record.decision != "approve"
        or not approval_matches_state(current.root, state, record)
    ):
        raise ValueError("execution_approval_invalid")
    return record


def _load_current_resource_plan(project: ResearchProject) -> dict[str, object]:
    """Reopen and revalidate the persisted Stage-11 resource plan."""
    current = _current_project(project)
    try:
        _path, raw = _load_validated_resource_plan(current)
        _plan, issues = validate_stage_eleven(current, raw)
    except (OSError, ValueError, TypeError) as error:
        raise ValueError("execution_prerequisites_changed") from error
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


def _build_execution_contract(project: ResearchProject) -> dict[str, object]:
    """Return a closed contract whose identity binds the current approved inputs."""
    current = _current_project(project)
    hashes = stage_twelve_artifact_hashes(current)
    plan = _load_current_resource_plan(current)
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
    project: ResearchProject, candidate: Mapping[str, object]
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
    if artifact is not None and (
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
        raise ValueError("execution_contract_invalid")
    if existing.get("contract_id") != _sha256(
        _canonical_json(_contract_id_payload(existing))
    ):
        raise ValueError("execution_contract_invalid")
    for field, value in candidate.items():
        if field != "created_at" and existing.get(field) != value:
            raise ValueError("execution_contract_invalid")
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
