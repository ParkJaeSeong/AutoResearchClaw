import json
from dataclasses import replace

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.approval import approve_current_gate, verify_current_approval
from researchclaw.core.project import ResearchProject
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import build_stage_twelve_project, complete_first_four_stages


def _project_at_stage_five_gate(root):
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    shortlist = project.root / "literature" / "shortlist.jsonl"
    shortlist.write_text(
        json.dumps(
            {
                "source_id": "source-1",
                "title": "Paper",
                "doi": "10.1/x",
                "decision": "include",
                "reason": "relevant",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    validate_current_stage(ResearchProject.open(project.root))
    return ResearchProject.open(project.root), shortlist


def test_stage_five_approval_advances_to_stage_six(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    record = approve_current_gate(project, "approve", "Use this corpus")

    reopened = ResearchProject.open(project.root)
    assert record.artifact_hashes["literature/shortlist.jsonl"]
    assert reopened.state.completed_stages[-1] == 5
    assert reopened.state.current_stage == 6
    assert reopened.state.status.value == "ready"
    assert reopened.state.next_action == "prepare_stage"
    assert verify_current_approval(project.root, record) is True
    persisted = json.loads((project.root / "approvals" / "stage-05.json").read_text(encoding="utf-8"))
    assert persisted["decision"] == "approve"


def test_modifying_shortlist_invalidates_approval(tmp_path):
    project, shortlist = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")
    shortlist.write_text(shortlist.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    assert verify_current_approval(project.root, record) is False


def test_reject_records_decision_without_advancing_gate(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    record = approve_current_gate(project, "reject", "Screen it again")

    reopened = ResearchProject.open(project.root)
    assert record.decision == "reject"
    assert reopened.state.current_stage == 5
    assert reopened.state.completed_stages == (1, 2, 3, 4)
    assert reopened.state.status.value == "needs_revision"


@pytest.mark.parametrize("decision", ["", "APPROVE", "defer"])
def test_approval_rejects_unknown_decisions(tmp_path, decision):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    with pytest.raises(ValueError, match="decision"):
        approve_current_gate(project, decision, "No")


def test_verification_rejects_a_record_with_an_unknown_decision(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")

    assert verify_current_approval(project.root, replace(record, decision="defer")) is False


def test_verification_rejects_missing_record_hashes(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")

    assert verify_current_approval(project.root, replace(record, artifact_hashes={})) is False


def test_verification_rejects_missing_persisted_stage_artifact(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")
    reopened = ResearchProject.open(project.root)
    state_without_shortlist = replace(
        reopened.state,
        artifacts={
            path: artifact
            for path, artifact in reopened.state.artifacts.items()
            if path != "literature/shortlist.jsonl"
        },
    )
    reopened.persist_state(state_without_shortlist)

    assert verify_current_approval(project.root, record) is False


def test_verification_rejects_future_gate_record_with_empty_hashes(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")

    assert verify_current_approval(project.root, replace(record, stage_id=9, artifact_hashes={})) is False


def test_verification_rejects_empty_record_when_stage_artifact_is_missing(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")
    record = approve_current_gate(project, "approve", "Use this corpus")
    reopened = ResearchProject.open(project.root)
    state_without_shortlist = replace(
        reopened.state,
        artifacts={
            path: artifact
            for path, artifact in reopened.state.artifacts.items()
            if path != "literature/shortlist.jsonl"
        },
    )
    reopened.persist_state(state_without_shortlist)

    assert verify_current_approval(project.root, replace(record, artifact_hashes={})) is False


def test_approve_cli_emits_only_json(tmp_path, capsys):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    assert main(["approve", str(project.root), "--decision", "approve", "--note", "Use it", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["stage_id"] == 5
    assert payload["decision"] == "approve"
    assert captured.err == ""


def test_approval_rejects_gate_symlink_even_when_content_matches(tmp_path):
    project, shortlist = _project_at_stage_five_gate(tmp_path / "demo")
    outside = tmp_path / "outside-shortlist.jsonl"
    outside.write_bytes(shortlist.read_bytes())
    shortlist.unlink()
    shortlist.symlink_to(outside)

    with pytest.raises(ValueError, match="unsafe artifact path"):
        approve_current_gate(project, "approve", "Use this corpus")


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_stage_twelve_approval_refuses_needs_input(tmp_path, decision):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / decision,
        readiness="needs_input",
    )

    with pytest.raises(ValueError, match="execution prerequisites are not ready"):
        approve_current_gate(project, decision, "Run it")


def test_execution_approval_binds_four_artifacts_without_executing(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    completed_before = project.state.completed_stages

    record = approve_current_gate(project, "approve", "Run it")

    assert set(record.artifact_hashes) == {
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
    }
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 12
    assert reopened.state.completed_stages == completed_before
    assert reopened.state.status.value == "ready"
    assert reopened.state.next_action == "report_resource_plan_milestone_only"
    assert reopened.status_dict()["approval_eligible"] is False
    assert not (project.root / "experiment/results.json").exists()
    assert json.loads(
        (project.root / "approvals/stage-12.json").read_text(encoding="utf-8")
    )["note"] == "Run it"
    handoff = reopened.build_handoff()
    assert handoff.next_action == "report_resource_plan_milestone_only"
    assert " approve " not in f" {handoff.next_command} "
    assert "stage prepare" not in handoff.next_command


def test_stage_twelve_approval_rechecks_readiness_against_current_inputs(tmp_path):
    project, declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")
    execution_gate = __import__(
        "researchclaw.core.execution_gate",
        fromlist=["recheck_execution_readiness"],
    )
    execution_gate.recheck_execution_readiness(project)
    declared_input.unlink()

    with pytest.raises(ValueError, match="execution prerequisites are not ready"):
        approve_current_gate(ResearchProject.open(project.root), "approve", "Run it")


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
    ],
)
def test_modifying_any_execution_gate_artifact_invalidates_approval(
    tmp_path,
    relative_path,
):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    record = approve_current_gate(project, "approve", "Run it")

    path = project.root / relative_path
    path.write_bytes(path.read_bytes() + b"\n")

    assert verify_current_approval(project.root, record) is False


def test_reject_keeps_stage_twelve_safely_locked(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")

    record = approve_current_gate(project, "reject", "Do not run")

    reopened = ResearchProject.open(project.root)
    assert record.note == "Do not run"
    assert reopened.state.current_stage == 12
    assert reopened.state.completed_stages[-1] == 11
    assert reopened.state.status.value == "needs_revision"
    assert reopened.state.next_action == "report_missing_execution_inputs"
    assert reopened.status_dict()["approval_eligible"] is False
    assert not (project.root / "experiment/results.json").exists()
    handoff = reopened.build_handoff()
    assert " approve " not in f" {handoff.next_command} "
