import json

from researchclaw.codex.cli import main
from researchclaw.core.knowledge_extraction import KnowledgeIssue
from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import prepare_task_packet
from researchclaw.core.validation import _as_validation_issue, validate_current_stage
from tests.codex_native.helpers import (
    build_completed_literature_gate_project,
    complete_first_four_stages,
    write_valid_fixture_artifacts,
)


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


def test_validation_rejects_output_symlink_even_when_content_is_valid(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)
    goal = project.root / "scope" / "goal.md"
    outside = tmp_path / "outside-goal.md"
    outside.write_bytes(goal.read_bytes())
    goal.unlink()
    goal.symlink_to(outside)

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} == {"unsafe_artifact_path"}
    assert "scope/goal.md" not in report.artifact_refs


def test_validation_records_failure_evidence_and_enforces_retry_limit(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")

    first = validate_current_stage(project)
    second = validate_current_stage(ResearchProject.open(project.root))

    assert first.attempt_number == 1
    assert first.retry_state == "retry_available"
    assert first.recommended_action == "revise_declared_outputs_and_validate_again"
    assert second.attempt_number == 2
    assert second.retry_state == "retry_limit_reached"
    reopened = ResearchProject.open(project.root)
    assert reopened.state.status.value == "blocked"
    assert reopened.state.retry_counts == {"1": 2}
    assert reopened.state.last_error == {
        "error_class": "blocked",
        "stage_id": 1,
        "attempt_number": 2,
        "issues": [issue.to_dict() for issue in second.issues],
        "artifact_hashes": {},
        "recommended_action": "review_failures_with_user",
        "retry_state": "retry_limit_reached",
    }


def test_validation_event_is_detailed_without_duplicate_prepare_event(tmp_path):
    from researchclaw.core.events import EventLog

    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")

    report = validate_current_stage(project)

    events = EventLog(project.root / "evaluation" / "events.jsonl").read_all()
    assert [event.type for event in events] == ["project_created", "validation_result"]
    payload = events[-1].payload
    assert payload["attempt_number"] == report.attempt_number
    assert payload["issues"] == [issue.to_dict() for issue in report.issues]
    assert payload["recommended_action"] == report.recommended_action
    assert payload["artifact_hashes"] == {}
    assert payload["retry_state"] == report.retry_state
    assert payload["error_state"] == "needs_revision"


def test_validation_reports_successful_retry_and_clears_last_error(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    assert validate_current_stage(project).valid is False
    write_valid_fixture_artifacts(project.root, 1)

    report = validate_current_stage(ResearchProject.open(project.root))

    assert report.valid is True
    assert report.attempt_number == 2
    assert report.retry_state == "succeeded_after_retry"
    assert ResearchProject.open(project.root).state.last_error is None


def test_stage_three_rejects_yaml_sequence_instead_of_a_mapping(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    for stage_id in range(1, 3):
        write_valid_fixture_artifacts(project.root, stage_id)
        assert validate_current_stage(project).valid is True
        project = ResearchProject.open(project.root)
    search_plan = project.root / "literature" / "search_plan.yaml"
    search_plan.parent.mkdir(parents=True, exist_ok=True)
    search_plan.write_text("- query one\n- query two\n", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert [issue.code for issue in report.issues] == ["invalid_format"]


def test_stage_four_rejects_non_string_source_metadata(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    for stage_id in range(1, 4):
        write_valid_fixture_artifacts(project.root, stage_id)
        assert validate_current_stage(project).valid is True
        project = ResearchProject.open(project.root)
    candidates = project.root / "literature" / "candidates.jsonl"
    candidates.write_text('{"title":42,"doi":123}\n', encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert [issue.code for issue in report.issues] == ["invalid_format"]


def test_stage_five_rejects_non_string_screening_metadata(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    project = complete_first_four_stages(project)
    shortlist = project.root / "literature" / "shortlist.jsonl"
    shortlist.write_text(
        '{"title":42,"decision":"include","reason":99}\n',
        encoding="utf-8",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert [issue.code for issue in report.issues] == ["invalid_format"]


def test_stage_six_hashes_valid_knowledge_artifacts_and_stops_at_stage_seven(tmp_path):
    project = build_completed_literature_gate_project(tmp_path / "demo")
    write_valid_fixture_artifacts(project.root, 6)

    report = validate_current_stage(project)

    assert report.valid is True
    assert set(report.artifact_refs) == {
        "knowledge/extractions.jsonl",
        "knowledge/extraction_manifest.json",
    }
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 7
    assert reopened.state.completed_stages == (1, 2, 3, 4, 5, 6)
    assert reopened.state.next_action == "report_knowledge_milestone_only"
    assert set(reopened.state.artifacts) >= set(report.artifact_refs)


def test_stage_six_invalid_extraction_needs_revision_then_blocks(tmp_path):
    project = build_completed_literature_gate_project(tmp_path / "demo")
    write_valid_fixture_artifacts(project.root, 6)
    (project.root / "knowledge" / "extractions.jsonl").write_text(
        '{"claim_id":"claim-1","source_id":"source-1"}\n',
        encoding="utf-8",
    )

    first = validate_current_stage(project)
    after_first = ResearchProject.open(project.root)
    second = validate_current_stage(after_first)

    assert first.valid is False
    assert first.error_state == "needs_revision"
    assert after_first.state.status.value == "needs_revision"
    assert {issue.code for issue in first.issues} == {"invalid_format"}
    assert {issue.path for issue in first.issues} == {"knowledge/extractions.jsonl"}
    assert second.valid is False
    assert second.error_state == "blocked"
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 6
    assert reopened.state.status.value == "blocked"
    assert reopened.state.retry_counts == {"6": 2}


def test_stage_six_accepts_empty_extractions_when_all_sources_are_unavailable(tmp_path):
    project = build_completed_literature_gate_project(tmp_path / "demo")
    write_valid_fixture_artifacts(project.root, 6)
    (project.root / "knowledge" / "extractions.jsonl").write_text("", encoding="utf-8")
    (project.root / "knowledge" / "extraction_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": project.state.project_id,
                "generated_at": "2026-08-27T12:00:00Z",
                "sources": [
                    {
                        "source_id": "source-1",
                        "decision": "include",
                        "access_status": "unavailable",
                        "accessed_at": None,
                        "access_url": None,
                        "claim_count": 0,
                        "failure_reason": "The source could not be retrieved",
                    }
                ],
                "summary": {
                    "included_sources": 1,
                    "processed_sources": 1,
                    "claim_count": 0,
                    "full_text_sources": 0,
                    "abstract_sources": 0,
                    "metadata_only_sources": 0,
                    "unavailable_sources": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    report = validate_current_stage(project)

    assert report.valid is True
    assert report.artifact_refs["knowledge/extractions.jsonl"].size == 0
    assert ResearchProject.open(project.root).state.current_stage == 7


def test_stage_six_issue_mapping_preserves_a_declared_output_path():
    issue = KnowledgeIssue(
        "invalid_format",
        "knowledge/extractions.jsonl",
        "claim is invalid",
    )

    mapped = _as_validation_issue(
        issue,
        ("knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"),
    )

    assert mapped.path == "knowledge/extractions.jsonl"
    assert mapped.code == issue.code
    assert mapped.message == issue.message


def test_stage_six_issue_mapping_routes_the_shortlist_input_to_the_manifest():
    issue = KnowledgeIssue(
        "invalid_format",
        "literature/shortlist.jsonl",
        "source identity is invalid",
    )

    mapped = _as_validation_issue(
        issue,
        ("knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"),
    )

    assert mapped.path == "knowledge/extraction_manifest.json"
    assert mapped.code == issue.code
    assert mapped.message == issue.message


def test_stage_six_issue_mapping_routes_an_unknown_path_to_the_manifest():
    issue = KnowledgeIssue("invalid_format", "unexpected/source.json", "unknown source issue")

    mapped = _as_validation_issue(
        issue,
        ("knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"),
    )

    assert mapped.path == "knowledge/extraction_manifest.json"
