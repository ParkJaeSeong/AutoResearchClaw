import json
from dataclasses import replace

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.approval import approve_current_gate, verify_current_approval
from researchclaw.core.project import ResearchProject
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import complete_first_four_stages


def _project_at_stage_five_gate(root):
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    shortlist = project.root / "literature" / "shortlist.jsonl"
    shortlist.write_text(
        json.dumps(
            {
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


def test_approval_completes_hash_bound_gate(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    record = approve_current_gate(project, "approve", "Use this corpus")

    reopened = ResearchProject.open(project.root)
    assert record.artifact_hashes["literature/shortlist.jsonl"]
    assert reopened.state.completed_stages[-1] == 5
    assert reopened.state.current_stage == 6
    assert reopened.state.status.value == "ready"
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
