from dataclasses import replace
import json

import pytest

from researchclaw.core.models import StageStatus
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.project import ResearchProject
from researchclaw.core.state import StateStore
from researchclaw.core.task_packets import prepare_task_packet
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import complete_first_four_stages, write_valid_fixture_artifacts


def _approved_project(root):
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    approve_current_gate(ResearchProject.open(project.root), "approve", "Approved")
    return ResearchProject.open(project.root)


def test_prepare_stage_one_packet_contains_no_model_backend(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    packet = prepare_task_packet(project)

    assert packet.schema_version == 1
    assert packet.stage_id == 1
    assert packet.name == "topic_init"
    assert packet.required_outputs == ("scope/goal.md", "scope/hardware_profile.json")
    serialized = packet.to_dict()
    assert "model" not in serialized
    assert "api_key" not in serialized
    assert "base_url" not in serialized


def test_packets_isolate_identical_outputs_under_distinct_project_roots(tmp_path):
    first = ResearchProject.create(tmp_path / "first", "Topic one", "materials_ai")
    second = ResearchProject.create(tmp_path / "second", "Topic two", "materials_ai")

    first_packet = prepare_task_packet(first).to_dict()
    second_packet = prepare_task_packet(second).to_dict()

    assert first_packet["project_root"] == str(first.root.resolve())
    assert second_packet["project_root"] == str(second.root.resolve())
    assert first_packet["project_root"] != second_packet["project_root"]
    assert first_packet["write_policy"] == "declared_outputs_only"
    assert second_packet["write_policy"] == "declared_outputs_only"
    assert first_packet["required_outputs"] == second_packet["required_outputs"]


def test_prepare_packet_refuses_completed_project(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    StateStore(project.root / ".researchclaw").save(replace(project.state, current_stage=24, status=StageStatus.COMPLETED))

    with pytest.raises(ValueError, match="project is complete"):
        prepare_task_packet(ResearchProject.open(project.root))


def test_prepare_stage_two_requires_state_artifacts_without_mutating_state(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    StateStore(project.root / ".researchclaw").save(replace(project.state, current_stage=2))
    project = ResearchProject.open(project.root)
    before = project.state

    with pytest.raises(ValueError, match="required input artifacts"):
        prepare_task_packet(project)

    assert project.state == before


def test_stage_prepare_cli_emits_packet_json(tmp_path, capsys):
    from researchclaw.codex.cli import main

    root = tmp_path / "demo"
    assert main(["init", str(root), "--topic", "Formation energy", "--json"]) == 0
    capsys.readouterr()
    assert main(["stage", "prepare", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage_id"] == 1
    assert "artifact_root" not in payload


def test_prepare_rejects_required_input_symlink_even_when_content_matches(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)
    assert validate_current_stage(project).valid is True
    project = ResearchProject.open(project.root)
    goal = project.root / "scope" / "goal.md"
    outside = tmp_path / "outside-goal.md"
    outside.write_bytes(goal.read_bytes())
    goal.unlink()
    goal.symlink_to(outside)

    with pytest.raises(ValueError, match="unsafe artifact path"):
        prepare_task_packet(project)


def test_prepare_rejects_required_input_changed_since_validation(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)
    assert validate_current_stage(project).valid is True
    project = ResearchProject.open(project.root)
    goal = project.root / "scope" / "goal.md"
    goal.write_text(
        goal.read_text(encoding="utf-8").replace("public", "secret"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="changed since validation"):
        prepare_task_packet(project)


def test_prepare_reopens_durable_state_instead_of_using_a_stale_project_value(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    write_valid_fixture_artifacts(project.root, 1)
    assert validate_current_stage(project).valid is True

    packet = prepare_task_packet(project)

    assert packet.stage_id == 2
    assert packet.required_inputs == ("scope/goal.md", "scope/hardware_profile.json")


def test_approved_project_prepares_stage_six_packet(tmp_path):
    project = _approved_project(tmp_path / "demo")

    packet = prepare_task_packet(ResearchProject.open(project.root))

    assert packet.stage_id == 6
    assert packet.required_inputs == ("literature/shortlist.jsonl",)
    assert packet.required_outputs == (
        "knowledge/extractions.jsonl",
        "knowledge/extraction_manifest.json",
    )


def test_stage_six_rejects_missing_approval(tmp_path):
    project = _approved_project(tmp_path / "demo")
    (project.root / "approvals" / "stage-05.json").unlink()

    with pytest.raises(ValueError, match="approved stage-5 shortlist"):
        prepare_task_packet(ResearchProject.open(project.root))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "reject"),
        ("project_id", "rc-wrong-project"),
        ("artifact_hashes", {"literature/shortlist.jsonl": "0" * 64}),
    ],
)
def test_stage_six_rejects_an_approval_record_that_no_longer_authorizes_shortlist(tmp_path, field, value):
    project = _approved_project(tmp_path / "demo")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval[field] = value
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(ValueError, match="approved stage-5 shortlist"):
        prepare_task_packet(ResearchProject.open(project.root))


def test_stage_six_rejects_malformed_approval_record(tmp_path):
    project = _approved_project(tmp_path / "demo")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="approved stage-5 shortlist"):
        prepare_task_packet(ResearchProject.open(project.root))
