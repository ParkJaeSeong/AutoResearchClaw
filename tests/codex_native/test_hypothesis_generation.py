import json

from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import build_task_packet
from researchclaw.core.validation import validate_current_stage
from researchclaw.core.hypotheses import validate_hypotheses

from tests.codex_native.helpers import (
    build_completed_synthesis_milestone_project,
    write_valid_fixture_artifacts,
)


def _candidate_lines(project) -> list[dict[str, object]]:
    path = project.root / "hypotheses" / "candidates.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_candidates(project, records: list[dict[str, object]]) -> None:
    path = project.root / "hypotheses" / "candidates.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_stage_eight_packet_declares_only_hypothesis_candidates(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")

    packet = build_task_packet(project)

    assert packet.stage_id == 8
    assert packet.name == "hypothesis_gen"
    assert packet.required_inputs == ("knowledge/synthesis.md",)
    assert packet.required_outputs == ("hypotheses/candidates.jsonl",)
    assert packet.allowed_tool_classes == ("filesystem", "research", "analysis")


def test_valid_stage_eight_advances_to_stage_nine_without_model_calls(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)

    report = validate_current_stage(project)
    reopened = ResearchProject.open(project.root)

    assert report.valid is True
    assert report.recommended_action == "report_hypothesis_milestone_only"
    assert reopened.state.current_stage == 9
    assert reopened.state.completed_stages == (1, 2, 3, 4, 5, 6, 7, 8)
    assert reopened.state.next_action == "report_hypothesis_milestone_only"


def test_stage_eight_milestone_does_not_request_unsupported_stage_nine_approval(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    report = validate_current_stage(project)
    assert report.valid is True

    handoff = ResearchProject.open(project.root).build_handoff()

    assert handoff.milestone_complete is True
    assert handoff.approval_required is False
    assert handoff.next_action == "report_hypothesis_milestone_only"
    assert handoff.write_policy == "no_undeclared_outputs"


def test_stage_eight_rejects_unknown_claim_and_gap_references(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    records[0]["claim_refs"] = ["claim-999"]
    records[1]["knowledge_gap_refs"] = ["gap-999"]
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "unknown_claim_reference",
        "unknown_knowledge_gap_reference",
    }


def test_stage_eight_requires_two_to_five_ranked_hypotheses(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)[:1]
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_hypothesis_count" for issue in report.issues)


def test_stage_eight_requires_quantified_prediction_and_falsification(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    records[0]["prediction"] = {
        "outcome": "test MAE",
        "direction": "increase",
        "magnitude": "",
        "measurement_context": "cell-grouped split",
    }
    records[1]["falsification_condition"] = ""
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "incomplete_prediction",
        "missing_falsification_condition",
    }


def test_stage_eight_requires_one_conventional_wisdom_challenge(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    for record in records:
        record["challenges_conventional_wisdom"] = False
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "missing_contrarian_hypothesis" for issue in report.issues)


def test_stage_eight_rejects_undeclared_candidate_fields(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    records[0]["generated_by"] = "external-model"
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "unknown_field" for issue in report.issues)


def test_stage_eight_rejects_undeclared_prediction_fields(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    records[0]["prediction"]["confidence"] = "high"
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "unknown_field" for issue in report.issues)


def test_stage_eight_rejects_placeholder_prediction_magnitude(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 8)
    records = _candidate_lines(project)
    records[0]["prediction"]["magnitude"] = "TBD for version 2"
    _write_candidates(project, records)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "non_quantified_prediction" for issue in report.issues)


def test_open_migrates_stage_seven_reporting_boundary_to_stage_eight_prepare(tmp_path):
    project = build_completed_synthesis_milestone_project(tmp_path / "project")
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_action"] = "report_synthesis_milestone_only"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    reopened = ResearchProject.open(project.root)

    assert reopened.state.current_stage == 8
    assert reopened.state.next_action == "prepare_stage"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["next_action"] == "prepare_stage"


def test_hypothesis_diagnostics_preserve_physical_jsonl_line_numbers():
    synthesis = "## Knowledge Gaps\n\n1. Gap [claim-1].\n2. Gap [claim-1].\n"
    invalid = json.loads(
        '{"hypothesis_id":"H001","rank":1,"statement":"test",'
        '"knowledge_gap_refs":["gap-1"],"claim_refs":["claim-1"],'
        '"novelty_argument":"test","rationale":"test",'
        '"prediction":{"outcome":"MAE","direction":"decrease","magnitude":"10%","measurement_context":"test"},'
        '"falsification_condition":"test","required_baselines":["base"],'
        '"feasibility":"test","confounders":["confounder"],'
        '"challenges_conventional_wisdom":true}'
    )
    invalid["statement"] = ""
    valid = {**invalid, "hypothesis_id": "H002", "rank": 2, "statement": "test"}
    candidates = "not-json\n" + json.dumps(invalid) + "\n" + json.dumps(valid) + "\n"

    issues = validate_hypotheses(synthesis, candidates)

    assert any(
        issue.code == "missing_required_field" and "line 2" in issue.message
        for issue in issues
    )
