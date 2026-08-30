from dataclasses import dataclass
from enum import Enum
import re
from collections.abc import Mapping

from .filesystem_baseline import FilesystemEntry
from .paths import validate_relative_path

_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_PROFILE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_ERROR_CLASSES = frozenset({"retryable", "needs_revision", "blocked"})
_NEXT_ACTIONS = frozenset(
    {
        "prepare_stage",
        "await_approval",
        "revise_declared_outputs_and_validate_again",
        "review_failures_with_user",
        "validate_stage",
        "report_foundation_milestone_only",
        "report_knowledge_milestone_only",
        "report_synthesis_milestone_only",
        "report_hypothesis_milestone_only",
        "report_validation_design_milestone_only",
        "report_computational_package_milestone_only",
        "report_resource_plan_milestone_only",
        "register_experiment_self_test",
        "approve_experiment_execution",
        "report_missing_execution_inputs",
        "prepare_run",
        "register_research_result",
    }
)
_EXECUTION_POLICIES = frozenset({"approval_required"})
_RETRY_STATES = frozenset(
    {
        "retry_available",
        "retry_limit_reached",
        "approval_invalidated",
        "artifact_invalidated",
        "stage_twelve_registration_recovery",
    }
)


class StageStatus(str, Enum):
    READY = "ready"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    NEEDS_REVISION = "needs_revision"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class StageTenSnapshot:
    status: str
    entries: tuple[FilesystemEntry, ...]


@dataclass(frozen=True)
class ProjectState:
    schema_version: int
    project_id: str
    topic: str
    profile: str
    current_stage: int
    status: StageStatus
    completed_stages: tuple[int, ...]
    next_action: str
    execution_policy: str
    artifacts: dict[str, ArtifactRef]
    retry_counts: dict[str, int]
    last_error: dict[str, object] | None
    stage_10_snapshot: StageTenSnapshot

    @classmethod
    def new(cls, project_id: str, topic: str, profile: str) -> "ProjectState":
        return cls(
            schema_version=1,
            project_id=project_id,
            topic=topic,
            profile=profile,
            current_stage=1,
            status=StageStatus.READY,
            completed_stages=(),
            next_action="prepare_stage",
            execution_policy="approval_required",
            artifacts={},
            retry_counts={},
            last_error=None,
            stage_10_snapshot=StageTenSnapshot("not_prepared", ()),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "topic": self.topic,
            "profile": self.profile,
            "current_stage": self.current_stage,
            "status": self.status.value,
            "completed_stages": list(self.completed_stages),
            "next_action": self.next_action,
            "execution_policy": self.execution_policy,
            "artifacts": {
                key: {"path": value.path, "sha256": value.sha256, "size": value.size}
                for key, value in self.artifacts.items()
            },
            "retry_counts": self.retry_counts,
            "last_error": self.last_error,
            "stage_10_snapshot": {
                "status": self.stage_10_snapshot.status,
                "entries": [
                    {
                        "path": entry.path,
                        "kind": entry.kind,
                        "sha256": entry.sha256,
                    }
                    for entry in self.stage_10_snapshot.entries
                ],
            },
        }

    @classmethod
    def from_dict(cls, data: object) -> "ProjectState":
        if not isinstance(data, dict):
            raise ValueError("state must be a JSON object")
        schema_version = _required_int(data, "schema_version", minimum=1, maximum=1)
        project_id = _required_string(data, "project_id")
        topic = _required_string(data, "topic")
        profile = _required_string(data, "profile")
        if _PROFILE_PATTERN.fullmatch(profile) is None:
            raise ValueError("state profile must be a lowercase identifier")
        current_stage = _required_int(data, "current_stage", minimum=1, maximum=24)
        status_value = _required_string(data, "status")
        try:
            status = StageStatus(status_value)
        except ValueError as error:
            raise ValueError(f"state status is invalid: {status_value}") from error
        completed_stages = _completed_stages(data.get("completed_stages"), current_stage)
        next_action = _required_string(data, "next_action")
        if next_action not in _NEXT_ACTIONS:
            raise ValueError(f"state next_action is invalid: {next_action}")
        execution_policy = _required_string(data, "execution_policy")
        if execution_policy not in _EXECUTION_POLICIES:
            raise ValueError(f"state execution_policy is invalid: {execution_policy}")
        artifacts = _artifacts(data.get("artifacts"))
        retry_counts = _retry_counts(data.get("retry_counts"))
        last_error = _last_error(data.get("last_error"))
        stage_10_snapshot = _stage_10_snapshot(data.get("stage_10_snapshot"))
        if current_stage == 24 and status is not StageStatus.COMPLETED:
            raise ValueError("state status must be completed at stage 24")
        if status is StageStatus.COMPLETED and current_stage != 24:
            raise ValueError("state current_stage must be 24 when status is completed")
        return cls(
            schema_version=schema_version,
            project_id=project_id,
            topic=topic,
            profile=profile,
            current_stage=current_stage,
            status=status,
            completed_stages=completed_stages,
            next_action=next_action,
            execution_policy=execution_policy,
            artifacts=artifacts,
            retry_counts=retry_counts,
            last_error=last_error,
            stage_10_snapshot=stage_10_snapshot,
        )


def _required_string(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"state {field} must be a non-empty string")
    return value


def _required_int(
    data: Mapping[str, object],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"state {field} must be an integer from {minimum} to {maximum}")
    return value


def _completed_stages(value: object, current_stage: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError("state completed_stages must be a JSON array")
    if any(not isinstance(stage, int) or isinstance(stage, bool) for stage in value):
        raise ValueError("state completed_stages must contain integers")
    stages = tuple(value)
    if stages != tuple(sorted(set(stages))):
        raise ValueError("state completed_stages must be strictly increasing")
    if any(stage < 1 or stage > 23 or stage >= current_stage for stage in stages):
        raise ValueError("state completed_stages must precede current_stage")
    return stages


def _artifacts(value: object) -> dict[str, ArtifactRef]:
    if not isinstance(value, dict):
        raise ValueError("state artifacts must be a JSON object")
    artifacts: dict[str, ArtifactRef] = {}
    for key, raw_artifact in value.items():
        if not isinstance(key, str) or not isinstance(raw_artifact, dict):
            raise ValueError("state artifact entries must be JSON objects keyed by path")
        path = raw_artifact.get("path")
        try:
            relative_path = validate_relative_path(path, kind="artifact")
        except ValueError as error:
            raise ValueError(f"state artifact path is invalid: {error}") from error
        if key != relative_path:
            raise ValueError("state artifact key must equal artifact path")
        sha256 = raw_artifact.get("sha256")
        if not isinstance(sha256, str) or _HASH_PATTERN.fullmatch(sha256) is None:
            raise ValueError(f"state artifact hash is invalid: {relative_path}")
        size = raw_artifact.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"state artifact size is invalid: {relative_path}")
        artifacts[key] = ArtifactRef(path=relative_path, sha256=sha256, size=size)
    return artifacts


def _retry_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("state retry_counts must be a JSON object")
    retry_counts: dict[str, int] = {}
    for key, count in value.items():
        if (
            not isinstance(key, str)
            or not key.isdigit()
            or key != str(int(key))
            or not 1 <= int(key) <= 23
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            raise ValueError("state retry_counts entries must map stage IDs to non-negative integers")
        retry_counts[key] = count
    return retry_counts


def _stage_10_snapshot(value: object) -> StageTenSnapshot:
    if value is None:
        return StageTenSnapshot("legacy_missing", ())
    if not isinstance(value, dict) or set(value) != {"status", "entries"}:
        raise ValueError("state stage_10_snapshot must be a closed JSON object")
    status = value.get("status")
    raw_entries = value.get("entries")
    if status not in {"not_prepared", "captured", "legacy_missing"}:
        raise ValueError("state stage_10_snapshot status is invalid")
    if not isinstance(raw_entries, list):
        raise ValueError("state stage_10_snapshot entries must be a JSON array")
    entries: list[FilesystemEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {
            "path",
            "kind",
            "sha256",
        }:
            raise ValueError("state stage_10_snapshot entry is invalid")
        try:
            path = validate_relative_path(raw_entry.get("path"), kind="snapshot path")
        except ValueError as error:
            raise ValueError(f"state snapshot path is invalid: {error}") from error
        kind = raw_entry.get("kind")
        sha256 = raw_entry.get("sha256")
        if kind not in {"directory", "regular_file", "symlink"}:
            raise ValueError(f"state snapshot kind is invalid: {path}")
        if kind == "directory":
            if sha256 is not None:
                raise ValueError(f"state directory snapshot hash must be null: {path}")
        elif not isinstance(sha256, str) or _HASH_PATTERN.fullmatch(sha256) is None:
            raise ValueError(f"state snapshot hash is invalid: {path}")
        entries.append(FilesystemEntry(path, kind, sha256))
    if entries != sorted(set(entries), key=lambda entry: entry.path) or len(
        {entry.path for entry in entries}
    ) != len(entries):
        raise ValueError("state snapshot entries must be path-sorted and unique")
    if status != "captured" and entries:
        raise ValueError("state uncaptured snapshot must not contain entries")
    return StageTenSnapshot(status, tuple(entries))


def _last_error(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("state last_error must be a JSON object or null")
    error_class = value.get("error_class")
    stage_id = value.get("stage_id")
    attempt_number = value.get("attempt_number")
    issues = value.get("issues")
    artifact_hashes = value.get("artifact_hashes")
    recommended_action = value.get("recommended_action")
    retry_state = value.get("retry_state")
    if error_class not in _ERROR_CLASSES:
        raise ValueError("state last_error error_class is invalid")
    if not isinstance(stage_id, int) or isinstance(stage_id, bool) or not 1 <= stage_id <= 23:
        raise ValueError("state last_error stage_id is invalid")
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
        raise ValueError("state last_error attempt_number is invalid")
    if not isinstance(issues, list):
        raise ValueError("state last_error issues must be a JSON array")
    normalized_issues: list[dict[str, str]] = []
    for issue in issues:
        if not isinstance(issue, dict) or any(
            not isinstance(issue.get(field), str) for field in ("code", "path", "message")
        ):
            raise ValueError("state last_error issues are invalid")
        normalized_issues.append(
            {field: issue[field] for field in ("code", "path", "message")}
        )
    if not isinstance(artifact_hashes, dict):
        raise ValueError("state last_error artifact_hashes must be a JSON object")
    normalized_hashes: dict[str, str] = {}
    for path, sha256 in artifact_hashes.items():
        try:
            relative_path = validate_relative_path(path, kind="artifact")
        except ValueError as error:
            raise ValueError(f"state last_error artifact path is invalid: {error}") from error
        if not isinstance(sha256, str) or _HASH_PATTERN.fullmatch(sha256) is None:
            raise ValueError("state last_error artifact hash is invalid")
        normalized_hashes[relative_path] = sha256
    if not isinstance(recommended_action, str) or not recommended_action:
        raise ValueError("state last_error recommended_action is invalid")
    if retry_state not in _RETRY_STATES:
        raise ValueError("state last_error retry_state is invalid")
    return {
        "error_class": error_class,
        "stage_id": stage_id,
        "attempt_number": attempt_number,
        "issues": normalized_issues,
        "artifact_hashes": normalized_hashes,
        "recommended_action": recommended_action,
        "retry_state": retry_state,
    }
