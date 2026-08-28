import json

import pytest

from researchclaw.core.approval import approve_current_gate
from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import build_task_packet
from researchclaw.core.validation import validate_current_stage

from tests.codex_native.helpers import (
    build_completed_hypothesis_milestone_project,
    write_valid_fixture_artifacts,
)


def _design(project) -> dict[str, object]:
    return json.loads((project.root / "experiment" / "design.json").read_text(encoding="utf-8"))


def _write_design(project, design: dict[str, object]) -> None:
    path = project.root / "experiment" / "design.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(design, ensure_ascii=False) + "\n", encoding="utf-8")


def test_stage_nine_packet_preserves_upstream_name_and_declares_validation_design(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")

    packet = build_task_packet(project)

    assert packet.stage_id == 9
    assert packet.name == "experiment_design"
    assert packet.objective == "Design a reproducible hypothesis validation"
    assert packet.required_inputs == ("hypotheses/candidates.jsonl",)
    assert packet.required_outputs == ("experiment/design.json",)
    assert packet.allowed_tool_classes == ("filesystem", "analysis")
    assert packet.requires_approval is True


def test_open_migrates_stage_eight_reporting_boundary_to_stage_nine_prepare(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_action"] = "report_hypothesis_milestone_only"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    reopened = ResearchProject.open(project.root)

    assert reopened.state.current_stage == 9
    assert reopened.state.next_action == "prepare_stage"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["next_action"] == "prepare_stage"


def test_valid_policy_design_stops_at_stage_nine_approval_gate(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)

    report = validate_current_stage(project)
    reopened = ResearchProject.open(project.root)

    assert report.valid is True
    assert report.recommended_action == "request_approval"
    assert reopened.state.current_stage == 9
    assert reopened.state.completed_stages == (1, 2, 3, 4, 5, 6, 7, 8)
    assert reopened.state.status.value == "awaiting_approval"
    assert reopened.state.next_action == "await_approval"


@pytest.mark.parametrize(
    ("validation_type", "method"),
    [
        (
            "computational",
            {
                "datasets": ["versioned public battery dataset"],
                "split_strategy": "cell-grouped held-out test split",
                "baselines": ["random row split"],
                "evaluation_protocol": "fit preprocessing on train only",
            },
        ),
        (
            "laboratory",
            {
                "materials": ["reference electrolyte formulation"],
                "controls": ["unmodified reference formulation"],
                "procedure": "randomized duplicate preparation and blinded measurement",
                "safety": "approved chemical hygiene and waste protocol",
            },
        ),
    ],
)
def test_stage_nine_accepts_each_declared_validation_type(tmp_path, validation_type, method):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["validation_type"] = validation_type
    design["method"] = method
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is True


def test_stage_nine_rejects_unknown_hypothesis_and_unquantified_metric(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["hypothesis_ids"] = ["H999"]
    design["metrics"][0]["target"] = "improve later"
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "unknown_hypothesis_reference",
        "non_quantified_metric",
    }


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_stage_nine_requires_integer_schema_version(tmp_path, schema_version):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["schema_version"] = schema_version
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_format" for issue in report.issues)


@pytest.mark.parametrize("validation_type", [["policy_evidence"], {}, True, 9])
def test_stage_nine_rejects_non_string_validation_type_without_crashing(
    tmp_path, validation_type
):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["validation_type"] = validation_type
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_validation_method" for issue in report.issues)


def test_stage_nine_rejects_numbers_that_are_not_metric_thresholds(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["metrics"][0]["target"] = "use protocol version 2"
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "non_quantified_metric" for issue in report.issues)


@pytest.mark.parametrize(
    "target",
    ["5 percentage points", "0.1 eV", "10 milliseconds", "300 kelvin", "0.8"],
)
def test_stage_nine_accepts_quantity_with_unit_as_metric_threshold(tmp_path, target):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["metrics"][0]["target"] = target
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is True


@pytest.mark.parametrize("validation_type", ["policy_evidence", "computational", "laboratory"])
def test_stage_nine_rejects_missing_type_specific_method(tmp_path, validation_type):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["validation_type"] = validation_type
    design["method"] = {}
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_validation_method" for issue in report.issues)


def test_stage_nine_rejects_undeclared_top_level_fields(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = _design(project)
    design["generated_by"] = "external-model"
    _write_design(project, design)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "unknown_field" for issue in report.issues)


def test_approved_stage_nine_stops_before_unsupported_stage_ten(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    report = validate_current_stage(project)
    assert report.valid is True

    record = approve_current_gate(ResearchProject.open(project.root), "approve", "Validation plan accepted")
    handoff = ResearchProject.open(project.root).build_handoff()

    assert record.stage_id == 9
    assert handoff.current_stage == 10
    assert handoff.completed_stages == (1, 2, 3, 4, 5, 6, 7, 8, 9)
    assert handoff.milestone_complete is True
    assert handoff.approval_required is False
    assert handoff.next_action == "report_validation_design_milestone_only"
    assert handoff.write_policy == "no_undeclared_outputs"
    reopened = ResearchProject.open(project.root)
    assert reopened.state.next_action == "report_validation_design_milestone_only"
    with pytest.raises(ValueError, match="not defined"):
        build_task_packet(reopened)
