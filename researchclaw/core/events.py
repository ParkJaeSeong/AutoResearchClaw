"""Durable, append-only evaluation events for local research projects."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .project import ResearchProject

_SCHEMA_VERSION = 1
_TOTAL_STAGES = 23


@dataclass(frozen=True)
class EvaluationEvent:
    """A versioned event emitted by the deterministic research workflow."""

    schema_version: int
    timestamp: str
    type: str
    project_id: str
    payload: dict[str, object]

    @classmethod
    def create(cls, event_type: str, project_id: str, payload: Mapping[str, object]) -> "EvaluationEvent":
        return cls(
            schema_version=_SCHEMA_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            type=event_type,
            project_id=project_id,
            payload=dict(payload),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "type": self.type,
            "project_id": self.project_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: object) -> "EvaluationEvent":
        if not isinstance(data, dict):
            raise ValueError("event must be a JSON object")
        schema_version = data.get("schema_version")
        timestamp = data.get("timestamp")
        event_type = data.get("type")
        project_id = data.get("project_id")
        payload = data.get("payload")
        if schema_version != _SCHEMA_VERSION:
            raise ValueError(f"unsupported event schema: {schema_version}")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError("event timestamp must be a non-empty string")
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event type must be a non-empty string")
        if not isinstance(project_id, str) or not project_id:
            raise ValueError("event project_id must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("event payload must be a JSON object")
        return cls(
            schema_version=schema_version,
            timestamp=timestamp,
            type=event_type,
            project_id=project_id,
            payload=payload,
        )


class EventLog:
    """An fsync-backed JSONL log that never rewrites existing events."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, event: EvaluationEvent) -> None:
        record = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read_all(self) -> list[EvaluationEvent]:
        if not self.path.exists():
            return []
        events: list[EvaluationEvent] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    data: Any = json.loads(line)
                    events.append(EvaluationEvent.from_dict(data))
                except (json.JSONDecodeError, ValueError) as error:
                    raise ValueError(f"malformed event at line {line_number}: {error}") from error
        return events


def event_log_for(project_root: Path) -> EventLog:
    """Return the standard evaluation log location for a project root."""
    return EventLog(Path(project_root) / "evaluation" / "events.jsonl")


def build_foundation_report(project: "ResearchProject") -> dict[str, object]:
    """Summarize foundation workflow metrics from durable project state and events."""
    events = event_log_for(project.root).read_all()
    state = project.state
    validation_failures = sum(
        event.type == "validation_result" and event.payload.get("valid") is False for event in events
    )
    approvals = sum(
        event.type == "approval_decision" and event.payload.get("decision") == "approve" for event in events
    )
    resumes = sum(event.type == "resume" for event in events)
    return {
        "project_id": state.project_id,
        "stage_completion_rate": len(state.completed_stages) / _TOTAL_STAGES,
        "validation_failure_count": validation_failures,
        "retry_count": sum(state.retry_counts.values()),
        "approval_count": approvals,
        "resume_count": resumes,
        "artifact_count": len(state.artifacts),
        "external_llm_calls": 0,
        "nested_agent_processes": 0,
    }
