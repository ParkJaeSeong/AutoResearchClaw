import json

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import prepare_task_packet
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import complete_first_four_stages, write_valid_fixture_artifacts


def test_stage_one_reports_missing_outputs_without_advancing(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} == {"missing_artifact"}
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 1
    assert reopened.state.completed_stages == ()
    assert reopened.state.status.value == "needs_revision"


def test_valid_stage_one_hashes_artifacts_and_advances(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)

    report = validate_current_stage(project)

    assert report.valid is True
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 2
    assert reopened.state.completed_stages == (1,)
    assert reopened.state.status.value == "ready"
    assert reopened.state.artifacts["scope/goal.md"].sha256 == report.artifact_refs["scope/goal.md"].sha256


def test_validation_and_task_packets_follow_exact_paths_through_stage_five(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    expected_outputs = (
        ("scope/goal.md", "scope/hardware_profile.json"),
        ("scope/problem_tree.md",),
        ("literature/search_plan.yaml",),
        ("literature/candidates.jsonl",),
        ("literature/shortlist.jsonl",),
    )

    for stage_id in range(1, 5):
        assert prepare_task_packet(project).required_outputs == expected_outputs[stage_id - 1]
        write_valid_fixture_artifacts(project.root, stage_id)
        assert validate_current_stage(project).valid is True
        project = ResearchProject.open(project.root)

    assert prepare_task_packet(project).required_outputs == expected_outputs[4]
    write_valid_fixture_artifacts(project.root, 5)
    report = validate_current_stage(project)

    assert report.valid is True
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 5
    assert reopened.state.completed_stages == (1, 2, 3, 4)
    assert reopened.state.status.value == "awaiting_approval"
    assert "literature/shortlist.jsonl" in reopened.state.artifacts


def test_invalid_candidate_line_marks_stage_for_revision(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    for stage_id in range(1, 4):
        write_valid_fixture_artifacts(project.root, stage_id)
        assert validate_current_stage(project).valid is True
        project = ResearchProject.open(project.root)
    (project.root / "literature" / "candidates.jsonl").write_text('{"title":"Missing identity"}\n', encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} == {"invalid_format"}
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 4
    assert reopened.state.completed_stages == (1, 2, 3)
    assert reopened.state.status.value == "needs_revision"


def test_stage_validate_cli_emits_json_report_and_failure_exit_code(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["init", str(root), "--topic", "Formation energy", "--json"]) == 0
    capsys.readouterr()

    assert main(["stage", "validate", str(root), "--json"]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["stage_id"] == 1
    assert payload["valid"] is False
    assert {issue["code"] for issue in payload["issues"]} == {"missing_artifact"}
    assert captured.err == ""


def test_stage_validate_cli_returns_zero_for_valid_stage(tmp_path, capsys):
    root = tmp_path / "demo"
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)

    assert main(["stage", "validate", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["valid"] is True
    assert payload["artifact_refs"]["scope/goal.md"]["path"] == "scope/goal.md"


def test_complete_first_four_stages_helper_reaches_stage_five_prerequisites(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")

    project = complete_first_four_stages(project)

    assert project.state.current_stage == 5
    assert project.state.completed_stages == (1, 2, 3, 4)
    assert prepare_task_packet(project).required_inputs == ("literature/candidates.jsonl",)
    assert prepare_task_packet(project).required_outputs == ("literature/shortlist.jsonl",)
