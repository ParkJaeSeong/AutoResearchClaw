import json

import pytest

from researchclaw.core.events import EvaluationEvent, EventLog


def test_event_log_preserves_order_and_payload(tmp_path):
    """Removing an append or changing its payload must be visible to readers."""
    log = EventLog(tmp_path / "events.jsonl")
    log.append(EvaluationEvent.create("project_created", "rc-test", {"profile": "materials_ai"}))
    log.append(EvaluationEvent.create("stage_validated", "rc-test", {"stage_id": 1, "valid": True}))

    events = log.read_all()

    assert [event.type for event in events] == ["project_created", "stage_validated"]
    assert events[1].payload == {"stage_id": 1, "valid": True}


def test_event_log_writes_one_compact_json_object_per_line(tmp_path):
    """Writing a non-JSON or split event record would break the append-only format."""
    path = tmp_path / "events.jsonl"
    EventLog(path).append(EvaluationEvent.create("project_created", "rc-test", {"profile": "materials_ai"}))

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "project_created"


def test_event_log_reports_malformed_line_number(tmp_path):
    """A corrupt event must identify its line so an operator can repair the log."""
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(EvaluationEvent.create("project_created", "rc-test", {"profile": "materials_ai"}).to_dict())
        + "\nnot-json\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 2"):
        EventLog(path).read_all()


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", "2026-08-27T12:00:00+09:00"],
    ids=["invalid_iso8601", "non_utc_offset"],
)
def test_event_log_rejects_non_utc_timestamps_with_line_number(tmp_path, timestamp):
    """Accepting malformed or non-UTC timestamps would corrupt ordered event data."""
    path = tmp_path / "events.jsonl"
    record = EvaluationEvent.create("project_created", "rc-test", {"profile": "materials_ai"}).to_dict()
    record["timestamp"] = timestamp
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        EventLog(path).read_all()
