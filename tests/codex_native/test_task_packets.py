from dataclasses import replace
import json

import pytest

from researchclaw.core.models import StageStatus
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.events import event_log_for
from researchclaw.core.project import ResearchProject
from researchclaw.core.state import StateStore
from researchclaw.core.task_packets import build_task_packet, prepare_task_packet
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import (
    build_completed_validation_design_project,
    complete_first_four_stages,
    write_valid_fixture_artifacts,
)


def _mark_stage_ten_state_as_legacy(project):
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.pop("stage_10_snapshot", None)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return ResearchProject.open(project.root)


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


def test_prepare_legacy_stage_ten_stays_fail_closed_by_default(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    legacy = _mark_stage_ten_state_as_legacy(project)

    with pytest.raises(ValueError, match="legacy.*snapshot"):
        prepare_task_packet(legacy)

    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "legacy_missing"


def test_prepare_can_explicitly_establish_safe_legacy_stage_ten_baseline(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    legacy = _mark_stage_ten_state_as_legacy(project)

    packet = prepare_task_packet(legacy, establish_legacy_baseline=True)

    assert packet.stage_id == 10
    snapshot = ResearchProject.open(project.root).state.stage_10_snapshot
    assert snapshot.status == "captured"
    assert snapshot.entries
    events = event_log_for(project.root).read_all()
    migration = [event for event in events if event.type == "legacy_stage_10_baseline_established"]
    assert len(migration) == 1
    assert migration[0].payload == {
        "entry_count": len(snapshot.entries),
        "stage_id": 10,
    }


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiment/code/main.py",
        "analysis.ipynb",
        "downloads/payload.bin",
        "data/downloaded.csv",
        "artifacts/model-results.json",
        "experiment/results.json",
        "experiment/results2.json",
        "experiment/modelresults.json",
        "downloadCache/payload.bin",
        "analysisOutput/table.csv",
        "notebook.ipynb.bak",
        "experiment/Code",
        "Package_Manifest",
        "EXPERIMENT/PACKAGE_MANIFEST.JSON",
        "artifacts/ｍｏｄｅｌｒｅｓｕｌｔｓ.json",
    ],
)
def test_prepare_refuses_legacy_baseline_when_stage_ten_artifacts_exist(
    tmp_path, relative_path
):
    project = build_completed_validation_design_project(tmp_path / "project")
    legacy = _mark_stage_ten_state_as_legacy(project)
    artifact = project.root / relative_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("untrusted", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing legacy Stage 10 baseline"):
        prepare_task_packet(legacy, establish_legacy_baseline=True)

    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "legacy_missing"


def test_prepare_refuses_legacy_baseline_flag_for_nonlegacy_state(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")

    with pytest.raises(ValueError, match="only valid for legacy-missing Stage 10"):
        prepare_task_packet(project, establish_legacy_baseline=True)


def test_stage_eleven_packet_includes_passive_hardware_and_deferred_execution_context(
    tmp_path,
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    project = ResearchProject.open(project.root)

    packet = build_task_packet(project)

    assert packet.stage_id == 11
    observation = json.loads(packet.profile_context["hardware_observation"][0])
    assert observation["method"] == "python_stdlib_passive"
    assert packet.profile_context["deferred_command"] == (
        "python experiment/code/main.py --config experiment/code/config.json",
    )
    assert packet.profile_context["result_path"] == ("experiment/results.json",)


def test_stage_eleven_packet_requires_current_stage_nine_approval(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    approval_path = project.root / "approvals" / "stage-09.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["decision"] = "reject"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(ValueError, match="approved stage-9 validation design"):
        build_task_packet(ResearchProject.open(project.root))


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


@pytest.mark.parametrize("symlink_kind", ("file", "parent"))
def test_prepare_rejects_a_symlinked_required_output_before_returning_packet(
    tmp_path,
    symlink_kind,
):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    outside = tmp_path / "outside"
    outside.mkdir()
    if symlink_kind == "parent":
        (project.root / "scope").symlink_to(outside, target_is_directory=True)
    else:
        (project.root / "scope").mkdir()
        (project.root / "scope" / "goal.md").symlink_to(outside / "goal.md")

    with pytest.raises(ValueError, match="unsafe artifact path"):
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
