import json
from dataclasses import replace

import pytest

from researchclaw.codex.cli import main as run_cli
from researchclaw.core import result_analysis, research_decision
from researchclaw.core.project import ResearchProject
from tests.codex_native.test_result_analysis import (
    _finalized_project,
    _register_analysis_rebuttals,
    _register_analysis_reviews,
    _valid_analysis_result,
    _write_analysis_submission,
)


def analyzed_project(path):
    project = _finalized_project(path)
    result_analysis.prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(
            project, "result.json", _valid_analysis_result(project)
        ),
    )
    return ResearchProject.open_readonly(project.root)


def test_decision_prepare_preserves_analysis_and_replays_exactly(tmp_path):
    project = analyzed_project(tmp_path / "project")
    report = project.root / "analysis/report.md"
    before = report.read_bytes()

    packet = research_decision.prepare_research_decision(project)

    assert packet["stage_id"] == 15
    assert packet["execution_allowed"] is False
    state = (project.root / ".researchclaw/state.json").read_bytes()
    assert research_decision.prepare_research_decision(project) == packet
    assert (project.root / ".researchclaw/state.json").read_bytes() == state
    assert report.read_bytes() == before


def test_decision_packet_closes_over_verified_analysis_history(tmp_path):
    project = analyzed_project(tmp_path / "project")

    packet = research_decision.prepare_research_decision(project)

    history = result_analysis.validate_completed_analysis(project)
    assert packet == {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "stage_id": 15,
        "inputs": {
            "analysis_records": history["references"],
            "research_evidence": history["evidence_packet"]["inputs"],
        },
        "roles": ["domain", "methodology", "critical_reproducibility"],
        "allowed_outputs": [
            "analysis/research-decision/reviews/domain.json",
            "analysis/research-decision/reviews/methodology.json",
            "analysis/research-decision/reviews/critical_reproducibility.json",
            "analysis/research-decision/rebuttals.json",
            "analysis/decision.json",
            "analysis/decision.md",
        ],
        "execution_allowed": False,
    }
    assert "phase" not in packet


@pytest.mark.parametrize(
    "record_path",
    [
        "analysis/evidence_packet.json",
        "analysis/results.json",
        "analysis/report.md",
        "analysis/reviews/domain.json",
        "analysis/reviews/methodology.json",
        "analysis/reviews/critical_reproducibility.json",
        "analysis/rebuttals.json",
    ],
)
def test_decision_prepare_rejects_changed_analysis_record(tmp_path, record_path):
    project = analyzed_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()
    (project.root / record_path).write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


@pytest.mark.parametrize(
    "target",
    [
        "final_selection",
        "council_decision",
        "baseline_manifest",
        "retained_stage_13_packet",
        "baseline_result",
        "approved_design",
        "approved_hypotheses",
    ],
)
def test_decision_prepare_rejects_changed_retained_analysis_input(tmp_path, target):
    project = analyzed_project(tmp_path / "project")
    inputs = result_analysis.validate_completed_analysis(project)["evidence_packet"][
        "inputs"
    ]
    paths = {
        "final_selection": inputs["final_selection"]["path"],
        "council_decision": inputs["council_decision"]["path"],
        "baseline_manifest": inputs["retained_manifests"][0]["path"],
        "retained_stage_13_packet": next(
            item["path"]
            for item in inputs["retained_evidence"]
            if item["path"] == "refinement/evidence_packet.json"
        ),
        "baseline_result": inputs["baseline_result"]["path"],
        "approved_design": inputs["approved_design"]["registered"]["path"],
        "approved_hypotheses": inputs["approved_hypotheses"]["path"],
    }
    before = (project.root / ".researchclaw/state.json").read_bytes()
    (project.root / paths[target]).write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_rejects_unregistered_analysis(tmp_path):
    project = analyzed_project(tmp_path / "project")
    project.persist_state(
        replace(
            project.state,
            artifacts={
                path: reference
                for path, reference in project.state.artifacts.items()
                if path != result_analysis.ANALYSIS_RESULT_PATH
            },
        )
    )
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(
            ResearchProject.open_readonly(project.root)
        )

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_rejects_wrong_stage(tmp_path):
    project = _finalized_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="decision_stage_invalid"):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_status_rejects_changed_packet(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    packet_path = project.root / research_decision.DECISION_PACKET_PATH
    packet_path.write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError, match="decision_packet_invalid"):
        research_decision.research_decision_status(project)


def test_decision_prepare_rejects_conflicting_existing_packet(tmp_path):
    project = analyzed_project(tmp_path / "project")
    packet_path = project.root / research_decision.DECISION_PACKET_PATH
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text('{"foreign":true}', encoding="utf-8")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="decision_packet_conflict"):
        research_decision.prepare_research_decision(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_recovers_exact_packet_after_interrupted_state_save(
    tmp_path, monkeypatch
):
    project = analyzed_project(tmp_path / "project")
    original = ResearchProject.persist_state
    interrupted = False

    def fail_packet_registration_once(self, state):
        nonlocal interrupted
        if (
            research_decision.DECISION_PACKET_PATH in state.artifacts
            and not interrupted
        ):
            interrupted = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_packet_registration_once)
    with pytest.raises(OSError, match="simulated interruption"):
        research_decision.prepare_research_decision(project)
    monkeypatch.setattr(ResearchProject, "persist_state", original)

    orphan = project.root / research_decision.DECISION_PACKET_PATH
    assert orphan.is_file()
    assert (
        research_decision.DECISION_PACKET_PATH
        not in ResearchProject.open_readonly(project.root).state.artifacts
    )

    packet = research_decision.prepare_research_decision(project)

    current = ResearchProject.open_readonly(project.root)
    assert research_decision.DECISION_PACKET_PATH in current.state.artifacts
    assert json.loads(orphan.read_text(encoding="utf-8")) == packet


def test_decision_prepare_rejects_output_symlink(tmp_path):
    project = analyzed_project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "analysis/research-decision").symlink_to(
        outside, target_is_directory=True
    )
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="unsafe artifact path"):
        research_decision.prepare_research_decision(project)

    assert not list(outside.iterdir())
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_status_without_packet_is_read_only(tmp_path):
    project = analyzed_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    status = research_decision.research_decision_status(project)

    assert status["phase"] == "awaiting_preparation"
    assert status["next_action"] == "prepare_research_decision"
    assert status["evidence_packet"] is None
    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_and_status_cli_use_evidence_only_language(tmp_path, capsys):
    project = analyzed_project(tmp_path / "project")

    assert run_cli(["decision", "prepare", str(project.root), "--json"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["stage_id"] == 15
    assert packet["execution_allowed"] is False

    assert run_cli(["decision", "status", str(project.root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence_packet"] == packet
    assert status["phase"] == "awaiting_independent_recommendations"

    assert run_cli(["decision", "--help"]) == 0
    help_text = capsys.readouterr().out
    assert "evidence-bound Stage 15 research decision" in help_text
    assert "run experiment" not in help_text.lower()
