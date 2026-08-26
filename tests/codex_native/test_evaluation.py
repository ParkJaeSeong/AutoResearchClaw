import json

from researchclaw.codex.cli import main
from researchclaw.core.events import EventLog, build_foundation_report
from researchclaw.core.project import ResearchProject
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import build_completed_literature_gate_project, write_valid_fixture_artifacts


def test_foundation_report_counts_retries_approvals_and_resume(tmp_path):
    """Dropping durable lifecycle events must change the derived report metrics."""
    project = build_completed_literature_gate_project(tmp_path / "demo")
    project.build_handoff()

    report = build_foundation_report(project)

    assert report["stage_completion_rate"] == 5 / 23
    assert report["approval_count"] == 1
    assert report["resume_count"] == 1
    assert report["retry_count"] == 0
    assert report["validation_failure_count"] == 0
    assert report["artifact_count"] == 6
    assert report["external_llm_calls"] == 0
    assert report["nested_agent_processes"] == 0


def test_foundation_report_counts_failed_then_successful_validation_as_retry(tmp_path):
    """A second validation of the same stage must be visible as a retry."""
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    assert validate_current_stage(project).valid is False
    write_valid_fixture_artifacts(project.root, 1)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True

    report = build_foundation_report(ResearchProject.open(project.root))

    assert report["retry_count"] == 1
    assert report["validation_failure_count"] == 1
    assert report["artifact_count"] == 2


def test_foundation_report_reopens_project_before_reading_state_metrics(tmp_path):
    """A caller's pre-validation project object must not produce stale metrics."""
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)
    assert validate_current_stage(project).valid is True

    report = build_foundation_report(project)

    assert report["stage_completion_rate"] == 1 / 23
    assert report["artifact_count"] == 2


def test_lifecycle_operations_append_evaluation_events(tmp_path):
    """Removing a lifecycle instrumentation point must leave a detectable gap."""
    project = build_completed_literature_gate_project(tmp_path / "demo")
    project.build_handoff()

    events = EventLog(project.root / "evaluation" / "events.jsonl").read_all()

    assert [event.type for event in events] == [
        "project_created",
        "validation_result",
        "validation_result",
        "validation_result",
        "validation_result",
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
