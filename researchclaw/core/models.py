from dataclasses import dataclass
from enum import Enum
from typing import cast


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
    last_error: dict[str, str] | None

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
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProjectState":
        if data.get("schema_version") != 1:
            raise ValueError(f"unsupported state schema: {data.get('schema_version')}")
        raw_artifacts = cast(dict[str, dict[str, object]], data.get("artifacts", {}))
        return cls(
            schema_version=1,
            project_id=str(data["project_id"]),
            topic=str(data["topic"]),
            profile=str(data["profile"]),
            current_stage=int(data["current_stage"]),
            status=StageStatus(str(data["status"])),
            completed_stages=tuple(int(value) for value in cast(list[object], data["completed_stages"])),
            next_action=str(data["next_action"]),
            execution_policy=str(data["execution_policy"]),
            artifacts={key: ArtifactRef(path=str(value["path"]), sha256=str(value["sha256"]), size=int(value["size"])) for key, value in raw_artifacts.items()},
            retry_counts={key: int(value) for key, value in cast(dict[str, object], data.get("retry_counts", {})).items()},
            last_error=cast(dict[str, str] | None, data.get("last_error")),
        )
