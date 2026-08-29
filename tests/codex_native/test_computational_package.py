import json

import pytest

from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import build_task_packet

from tests.codex_native.helpers import build_completed_validation_design_project


def test_stage_ten_packet_declares_fixed_computational_package(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")

    packet = build_task_packet(project)

    assert packet.stage_id == 10
    assert packet.name == "code_generation"
    assert packet.required_inputs == ("experiment/design.json",)
    assert packet.required_outputs == (
        "experiment/package_manifest.json",
        "experiment/code/README.md",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/code/requirements.txt",
        "experiment/code/tests/test_smoke.py",
    )
    assert packet.allowed_tool_classes == ("filesystem", "analysis")
    assert packet.requires_approval is False


@pytest.mark.parametrize("validation_type", ["policy_evidence", "laboratory"])
def test_stage_ten_rejects_deferred_validation_types(tmp_path, validation_type):
    project = build_completed_validation_design_project(
        tmp_path / "project", validation_type=validation_type
    )

    with pytest.raises(ValueError, match=f"stage 10 does not support {validation_type}"):
        build_task_packet(project)


def test_stage_ten_requires_current_stage_nine_approval(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    (project.root / "approvals" / "stage-09.json").unlink()

    with pytest.raises(
        ValueError, match="stage 10 requires the approved stage-9 validation design"
    ):
        build_task_packet(project)


def test_open_migrates_stage_ten_validation_design_report_to_prepare(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_action"] = "report_validation_design_milestone_only"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    reopened = ResearchProject.open(project.root)

    assert reopened.state.current_stage == 10
    assert reopened.state.next_action == "prepare_stage"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["next_action"] == "prepare_stage"
