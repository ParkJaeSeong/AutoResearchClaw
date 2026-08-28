import json
import subprocess
import sys
import shlex
from hashlib import sha256
from dataclasses import replace

import pytest

from researchclaw.core.approval import approve_current_gate
from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.state import StateStore
from researchclaw.core.task_packets import prepare_task_packet
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import (
    build_completed_knowledge_milestone_project,
    complete_first_four_stages,
    write_valid_fixture_artifacts,
)


def _resume(root):
    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "resume", str(root), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def _approved_project(root):
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    approve_current_gate(ResearchProject.open(project.root), "approve", "Approved")
    return ResearchProject.open(project.root)


def _persist_legacy_approved_shortlist(
    project,
    shortlist_text,
    *,
    next_action="prepare_stage",
):
    shortlist_path = project.root / "literature" / "shortlist.jsonl"
    payload = shortlist_text.encode("utf-8")
    shortlist_path.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    state = replace(
        project.state,
        next_action=next_action,
        artifacts={
            **project.state.artifacts,
            "literature/shortlist.jsonl": ArtifactRef(
                path="literature/shortlist.jsonl",
                sha256=digest,
                size=len(payload),
            ),
        },
    )
    StateStore(project.root / ".researchclaw").save(state)
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"]["literature/shortlist.jsonl"] = digest
    approval_path.write_text(json.dumps(approval), encoding="utf-8")


def test_resume_uses_only_project_files(tmp_path):
    project = ResearchProject.create(tmp_path / "demo project", "Formation energy", "materials_ai")
    complete_first_four_stages(project)

    payload = _resume(project.root)
    assert payload["current_stage"] == 5
    assert shlex.split(payload["next_command"]) == [
        "researchclaw-codex",
        "stage",
        "prepare",
        str(project.root),
        "--json",
    ]
    assert "conversation" not in json.dumps(payload).lower()


def test_resume_rehashes_persisted_artifacts_before_preparing(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    goal = project.root / "scope" / "goal.md"
    goal.write_text("# Changed\n\nDifferent goal.\n", encoding="utf-8")

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"
    assert shlex.split(payload["next_command"]) == [
        "researchclaw-codex",
        "stage",
        "validate",
        str(project.root),
        "--json",
    ]


def test_resume_points_an_unapproved_gate_to_approve(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True

    payload = _resume(project.root)

    assert payload["status"] == "awaiting_approval"
    assert shlex.split(payload["next_command"])[0:3] == [
        "researchclaw-codex",
        "approve",
        str(project.root),
    ]


def test_resume_rejects_artifact_paths_outside_the_project(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    state = ResearchProject.open(project.root).state
    ResearchProject.open(project.root).persist_state(
        replace(
            state,
            artifacts={
                "../outside.md": ArtifactRef(
                    path="../outside.md",
                    sha256="31207a2065f46a5b948fce6fe5c13e85abaf5631e2f894b47dcd4fce14f6c57b",
                    size=7,
                )
            },
        )
    )

    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "resume", str(project.root), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "artifact path" in result.stderr


def test_resume_rechecks_completed_gate_approval_records(tmp_path):
    project = _approved_project(tmp_path / "demo")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"]["literature/shortlist.jsonl"] = "0" * 64
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"
    assert shlex.split(payload["next_command"])[0:4] == [
        "researchclaw-codex",
        "stage",
        "validate",
        str(project.root),
    ]


def test_resume_rejects_a_valid_different_stage_approval_record(tmp_path):
    project = _approved_project(tmp_path / "demo")
    stage_nine_artifact = project.root / "experiment" / "design.json"
    stage_nine_artifact.parent.mkdir()
    stage_nine_artifact.write_text("{}", encoding="utf-8")
    state = ResearchProject.open(project.root).state
    ResearchProject.open(project.root).persist_state(
        replace(
            state,
            artifacts={
                **state.artifacts,
                "experiment/design.json": ArtifactRef(
                    path="experiment/design.json",
                    sha256=sha256(b"{}").hexdigest(),
                    size=2,
                ),
            },
        )
    )
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["stage_id"] = 9
    approval["artifact_hashes"] = {"experiment/design.json": sha256(b"{}").hexdigest()}
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"


def test_resume_returns_revision_json_for_malformed_approval_hashes(tmp_path):
    project = _approved_project(tmp_path / "demo")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"] = []
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "resume", str(project.root), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_revision"
    assert result.stderr == ""


def test_resume_prepares_stage_six_for_an_approved_shortlist(tmp_path):
    project = _approved_project(tmp_path / "demo")

    payload = _resume(project.root)

    assert payload["current_stage"] == 6
    assert payload["milestone_complete"] is False
    assert payload["next_action"] == "prepare_stage"
    assert payload["project_root"] == str(project.root.resolve())
    assert payload["write_policy"] == "declared_outputs_only"
    assert shlex.split(payload["next_command"]) == [
        "researchclaw-codex",
        "stage",
        "prepare",
        str(project.root),
        "--json",
    ]


def test_open_migrates_legacy_foundation_action_only_for_a_valid_stage_five_approval(tmp_path):
    project = _approved_project(tmp_path / "demo")
    legacy_state = replace(project.state, next_action="report_foundation_milestone_only")
    StateStore(project.root / ".researchclaw").save(legacy_state)

    reopened = ResearchProject.open(project.root)
    persisted = json.loads((project.root / ".researchclaw" / "state.json").read_text(encoding="utf-8"))

    assert reopened.state.next_action == "prepare_stage"
    assert persisted["next_action"] == "prepare_stage"


def test_open_keeps_legacy_foundation_action_when_stage_five_approval_is_invalid(tmp_path):
    project = _approved_project(tmp_path / "demo")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"]["literature/shortlist.jsonl"] = "0" * 64
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    StateStore(project.root / ".researchclaw").save(
        replace(project.state, next_action="report_foundation_milestone_only")
    )

    reopened = ResearchProject.open(project.root)
    persisted = json.loads((project.root / ".researchclaw" / "state.json").read_text(encoding="utf-8"))

    assert reopened.state.next_action == "report_foundation_milestone_only"
    assert persisted["next_action"] == "report_foundation_milestone_only"


def test_open_rewinds_a_legacy_approval_for_an_all_excluded_shortlist_before_migration(tmp_path):
    project = _approved_project(tmp_path / "demo")
    _persist_legacy_approved_shortlist(
        project,
        '{"source_id":"source-1","title":"Paper","doi":"10.1/x","decision":"exclude","reason":"out of scope"}\n',
        next_action="report_foundation_milestone_only",
    )

    reopened = ResearchProject.open(project.root)

    assert reopened.state.current_stage == 5
    assert reopened.state.status.value == "needs_revision"
    assert reopened.state.completed_stages == (1, 2, 3, 4)
    assert reopened.state.next_action == "validate_stage"
    assert "at least one included source" in json.dumps(reopened.state.last_error)


def test_prepare_rewinds_a_legacy_approval_without_source_identity_before_stage_six_packet(tmp_path):
    project = _approved_project(tmp_path / "demo")
    _persist_legacy_approved_shortlist(
        project,
        '{"title":"Paper","doi":"10.1/x","decision":"include","reason":"relevant"}\n',
    )

    packet = prepare_task_packet(project)

    assert packet.stage_id == 5
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 5
    assert reopened.state.status.value == "needs_revision"
    assert reopened.state.retry_counts.get("6") is None


def test_resume_rewinds_modified_approved_gate_for_validation_and_new_approval(tmp_path):
    project = _approved_project(tmp_path / "demo")
    shortlist = project.root / "literature" / "shortlist.jsonl"
    shortlist.write_text(shortlist.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    payload = _resume(project.root)

    assert payload["current_stage"] == 5
    assert payload["status"] == "needs_revision"
    assert payload["milestone_complete"] is False
    assert shlex.split(payload["next_command"])[0:4] == [
        "researchclaw-codex",
        "stage",
        "validate",
        str(project.root),
    ]
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 5
    assert reopened.state.completed_stages == (1, 2, 3, 4)


def test_resume_rewinds_approved_gate_when_artifact_becomes_matching_symlink(tmp_path):
    project = _approved_project(tmp_path / "demo")
    shortlist = project.root / "literature" / "shortlist.jsonl"
    outside = tmp_path / "outside-shortlist.jsonl"
    outside.write_bytes(shortlist.read_bytes())
    shortlist.unlink()
    shortlist.symlink_to(outside)

    payload = _resume(project.root)

    assert payload["current_stage"] == 5
    assert payload["status"] == "needs_revision"
    assert ResearchProject.open(project.root).state.completed_stages == (1, 2, 3, 4)


def test_resume_prepares_synthesis_at_stage_seven(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "demo")

    payload = _resume(project.root)

    assert payload["current_stage"] == 7
    assert payload["completed_stages"] == [1, 2, 3, 4, 5, 6]
    assert payload["milestone_complete"] is False
    assert payload["next_action"] == "prepare_stage"
    assert payload["write_policy"] == "declared_outputs_only"
    assert shlex.split(payload["next_command"]) == [
        "researchclaw-codex",
        "stage",
        "prepare",
        str(project.root),
        "--json",
    ]


def test_stage_seven_task_packet_is_available_at_the_supported_boundary(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "demo")

    packet = prepare_task_packet(project)
    assert packet.stage_id == 7
    assert packet.required_outputs == ("knowledge/synthesis.md",)
