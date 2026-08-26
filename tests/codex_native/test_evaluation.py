import json

from researchclaw.codex.cli import main
from researchclaw.core.events import EventLog, build_foundation_report
from tests.codex_native.helpers import build_completed_literature_gate_project


def test_foundation_report_counts_retries_approvals_and_resume(tmp_path):
    """Dropping durable lifecycle events must change the derived report metrics."""
    project = build_completed_literature_gate_project(tmp_path / "demo")
    project.build_handoff()

    report = build_foundation_report(project)

    assert report["stage_completion_rate"] == 5 / 23
    assert report["approval_count"] == 1
    assert report["resume_count"] == 1
    assert report["external_llm_calls"] == 0
    assert report["nested_agent_processes"] == 0


def test_lifecycle_operations_append_evaluation_events(tmp_path):
    """Removing a lifecycle instrumentation point must leave a detectable gap."""
    project = build_completed_literature_gate_project(tmp_path / "demo")
    project.build_handoff()

    events = EventLog(project.root / "evaluation" / "events.jsonl").read_all()

    assert [event.type for event in events] == [
        "project_created",
        "task_packet_prepared",
        "validation_result",
        "task_packet_prepared",
        "validation_result",
        "task_packet_prepared",
        "validation_result",
        "task_packet_prepared",
        "validation_result",
        "task_packet_prepared",
        "validation_result",
        "approval_decision",
        "resume",
    ]


def test_evaluate_cli_emits_only_report_json(tmp_path, capsys):
    """Evaluation event writes must not contaminate machine-readable CLI output."""
    project = build_completed_literature_gate_project(tmp_path / "demo")

    assert main(["evaluate", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["project_id"] == project.state.project_id
    assert report["approval_count"] == 1
    assert captured.err == ""
