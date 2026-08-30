"""Durable, append-only evaluation events for local research projects."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .project import ResearchProject

_SCHEMA_VERSION = 1
_TOTAL_STAGES = 23
_REGISTRATION_PENDING_NAME = "research-result-registration.pending.json"
MAX_EVENT_RECORD_BYTES = 64 * 1024


def _reject_duplicate_event_keys(
    pairs: list[tuple[object, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if not isinstance(key, str) or key in value:
            raise ValueError("event JSON keys must be unique strings")
        value[key] = item
    return value


def _reject_event_constant(_value: str) -> object:
    raise ValueError("event JSON numbers must be finite")


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
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp)
        except ValueError as error:
            raise ValueError("event timestamp must be ISO-8601") from error
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != timedelta(0):
            raise ValueError("event timestamp must use a UTC offset")
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
        """Append under the common project mutation transaction."""
        from .transactions import project_transaction

        if self._registration_pending_path() is None:
            self._append_record(event)
            return
        project_root = self.path.parent.parent
        with project_transaction(project_root):
            self._append_record(event)

    def _append_record(self, event: EvaluationEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_WRONLY
            | os.O_APPEND
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        try:
            self._write_record(descriptor, event)
        finally:
            os.close(descriptor)

    def append_locked(
        self, event: EvaluationEvent, *, expected_offset: int
    ) -> int:
        """Append at an exact offset while the caller owns the event-log flock."""
        descriptor = os.open(
            self.path,
            os.O_WRONLY
            | os.O_APPEND
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        try:
            actual_offset = os.fstat(descriptor).st_size
            if actual_offset != expected_offset:
                raise ValueError("event log changed before locked append")
            self._write_record(descriptor, event)
            return actual_offset
        finally:
            os.close(descriptor)

    def _registration_pending_path(self) -> Path | None:
        if self.path.name != "events.jsonl" or self.path.parent.name != "evaluation":
            return None
        return (
            self.path.parent.parent
            / ".researchclaw"
            / _REGISTRATION_PENDING_NAME
        )

    @staticmethod
    def _bounded_record(event: EvaluationEvent) -> bytes:
        encoder = json.JSONEncoder(
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        chunks: list[bytes] = []
        size = 1
        for text_chunk in encoder.iterencode(event.to_dict()):
            for start in range(0, len(text_chunk), 4096):
                chunk = text_chunk[start : start + 4096].encode("utf-8")
                size += len(chunk)
                if size > MAX_EVENT_RECORD_BYTES:
                    raise ValueError("event_record_too_large")
                chunks.append(chunk)
        return b"".join(chunks) + b"\n"

    @staticmethod
    def _write_record(descriptor: int, event: EvaluationEvent) -> None:
        record = EventLog._bounded_record(event)
        written = 0
        while written < len(record):
            count = os.write(descriptor, record[written:])
            if count <= 0:
                raise OSError("event log append made no progress")
            written += count
        os.fsync(descriptor)

    def iter_events(self):
        """Yield bounded JSONL records without loading the whole log."""
        if not self.path.exists():
            return
        descriptor = os.open(
            self.path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("event log must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                line_number = 0
                while True:
                    line = handle.readline(MAX_EVENT_RECORD_BYTES + 1)
                    if not line:
                        break
                    line_number += 1
                    if len(line) > MAX_EVENT_RECORD_BYTES:
                        raise ValueError(
                            f"malformed event at line {line_number}: record is too large"
                        )
                    if not line.endswith(b"\n"):
                        raise ValueError(
                            f"malformed event at line {line_number}: incomplete record"
                        )
                    try:
                        data: Any = json.loads(
                            line.decode("utf-8"),
                            object_pairs_hook=_reject_duplicate_event_keys,
                            parse_constant=_reject_event_constant,
                        )
                        yield EvaluationEvent.from_dict(data)
                    except (
                        UnicodeError,
                        json.JSONDecodeError,
                        ValueError,
                        RecursionError,
                    ) as error:
                        raise ValueError(
                            f"malformed event at line {line_number}: {error}"
                        ) from error
        finally:
            os.close(descriptor)

    def read_all(self) -> list[EvaluationEvent]:
        return list(self.iter_events())


def event_log_for(project_root: Path) -> EventLog:
    """Return the standard evaluation log location for a project root."""
    return EventLog(Path(project_root) / "evaluation" / "events.jsonl")


def build_foundation_report(project: "ResearchProject") -> dict[str, object]:
    """Summarize foundation workflow metrics from durable project state and events."""
    from .project import ResearchProject

    current_project = ResearchProject.open(project.root)
    events = event_log_for(current_project.root).read_all()
    state = current_project.state
    validation_failures = sum(
        event.type == "validation_result" and event.payload.get("valid") is False for event in events
    )
    approvals = sum(
        event.type == "approval_decision" and event.payload.get("decision") == "approve" for event in events
    )
    resumes = sum(event.type == "resume" for event in events)
    validation_attempts: dict[int, int] = {}
    for event in events:
        stage_id = event.payload.get("stage_id")
        if event.type == "validation_result" and isinstance(stage_id, int) and not isinstance(stage_id, bool):
            validation_attempts[stage_id] = validation_attempts.get(stage_id, 0) + 1
    return {
        "project_id": state.project_id,
        "stage_completion_rate": len(state.completed_stages) / _TOTAL_STAGES,
        "validation_failure_count": validation_failures,
        "retry_count": sum(attempts - 1 for attempts in validation_attempts.values()),
        "approval_count": approvals,
        "resume_count": resumes,
        "artifact_count": len(state.artifacts),
        "external_llm_calls": 0,
        "nested_agent_processes": 0,
    }
