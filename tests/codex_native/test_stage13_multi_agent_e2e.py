"""Synthetic public-CLI proof of the Stage 13 council workflow."""

import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
from researchclaw.llm.client import LLMClient
from tests.codex_native.helpers import (
    build_stage_thirteen_project,
    immutable_stage_twelve_snapshot,
    write_refinement_candidate,
)
from tests.codex_native.test_refinement import (
    valid_assessment_record,
    valid_decision_record,
    valid_envelope,
    valid_rebuttals_record,
)
from tests.codex_native.test_refinement_execution import write_refinement_result


ROOT = Path(__file__).parents[2]
REFINEMENT_REFERENCE = ROOT / "skills" / "researchclaw" / "references" / "refinement.md"
VOTING_ROLES = ("domain", "methodology", "critical_reproducibility")


def _write_record(project, relative_path, payload):
    path = project.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return relative_path


def _run_json(capsys, *argv):
    assert main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def _register_assessments(capsys, project, *, submission_prefix, artifacts=None):
    for role in VOTING_ROLES:
        assessment = _write_record(
            project,
            f"submissions/{submission_prefix}-{role}.json",
            valid_assessment_record(project, role=role, artifacts=artifacts),
        )
        _run_json(
            capsys,
            "refinement",
            "register-assessment",
            str(project.root),
            "--assessment",
            assessment,
            "--json",
        )
    rebuttals = _write_record(
        project,
        f"submissions/{submission_prefix}-rebuttals.json",
        valid_rebuttals_record(project),
    )
    return _run_json(
        capsys,
        "refinement",
        "register-deliberation",
        str(project.root),
        "--rebuttals",
        rebuttals,
        "--json",
    )


def _decision_for(project, *, action, candidate_id):
    decision = valid_decision_record(
        project,
        votes=(action, action, "inconclusive"),
        candidate_id=candidate_id,
    )
    decision.update(
        action=action,
        candidate_id=candidate_id,
        supporting_roles=["domain", "methodology"],
        dissenting_roles=["critical_reproducibility"],
        rationale=["Two independent voters support this recorded outcome."],
        limitations=["The result remains limited to registered inputs."],
        stage_14_questions=["Does the conclusion survive sensitivity analysis?"],
    )
    decision.pop("change_request", None)
    return decision


def test_stage13_council_cli_e2e_refines_selects_and_preserves_baseline(
    tmp_path, capsys, monkeypatch
):
    """Exercise the documented user-mediated protocol without network or LLM clients."""
    # The public user entry must exist before this synthetic workflow is usable.
    assert "researchclaw-codex refinement" in REFINEMENT_REFERENCE.read_text().lower()

    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("Stage 13 orchestration must not access a network")

    llm_client_calls = []

    def forbidden_llm_client(*_args, **_kwargs):
        llm_client_calls.append("attempted")
        raise AssertionError("Stage 13 orchestration must not configure an LLM client")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(LLMClient, "__init__", forbidden_llm_client)

    project = build_stage_thirteen_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    envelope = _write_record(project, "refinement/envelope.json", valid_envelope())
    _run_json(
        capsys,
        "refinement",
        "prepare-session",
        str(project.root),
        "--envelope",
        envelope,
        "--json",
    )

    _register_assessments(capsys, project, submission_prefix="initial")
    refine_decision = _write_record(
        project,
        "submissions/refine.json",
        valid_decision_record(project),
    )
    _run_json(
        capsys,
        "refinement",
        "register-decision",
        str(project.root),
        "--decision",
        refine_decision,
        "--json",
    )

    manifest = write_refinement_candidate(project)
    _run_json(
        capsys,
        "refinement",
        "register-candidate",
        str(project.root),
        "--manifest",
        str(manifest.relative_to(project.root)),
        "--json",
    )
    self_test = _run_json(
        capsys,
        "refinement",
        "prepare-self-test",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--json",
    )
    completed = subprocess.run(
        self_test["argv"],
        cwd=self_test["cwd"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    _run_json(
        capsys,
        "refinement",
        "register-self-test",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--report",
        self_test["report_path"],
        "--confirm-refinement-self-test",
        "--json",
    )

    run = _run_json(
        capsys,
        "refinement",
        "prepare-run",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--json",
    )
    write_refinement_result(project, SimpleNamespace(**run), elapsed_seconds=1.0)
    candidate_result = _run_json(
        capsys,
        "refinement",
        "register-result",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--result",
        run["result_path"],
        "--confirm-refinement-result",
        "--json",
    )
    candidate_manifest = candidate_result["evidence_manifest_path"]
    assert candidate_result["wall_seconds_used"] == 1.0

    reopened = ResearchProject.open(project.root)
    result = reopened.state.artifacts[run["result_path"]]
    evaluated = [
        {
            "path": "refinement/evidence_packet.json",
            "sha256": json.loads(
                (project.root / "refinement/session.json").read_text(encoding="utf-8")
            )["evidence_packet"]["sha256"],
            "size": (project.root / "refinement/evidence_packet.json").stat().st_size,
        },
        {"path": result.path, "sha256": result.sha256, "size": result.size},
    ]
    _register_assessments(
        capsys, project, submission_prefix="selection", artifacts=evaluated
    )
    final_decision_payload = _decision_for(
        project, action="select_candidate", candidate_id="candidate-001"
    )
    final_decision_payload["evidence_refs"] = [item["path"] for item in evaluated]
    for vote in final_decision_payload["final_votes"]:
        vote["evidence_refs"] = [item["path"] for item in evaluated]
    final_decision = _write_record(
        project, "submissions/final-selection.json", final_decision_payload
    )
    _run_json(
        capsys,
        "refinement",
        "register-decision",
        str(project.root),
        "--decision",
        final_decision,
        "--json",
    )
    _run_json(
        capsys,
        "refinement",
        "finalize",
        str(project.root),
        "--decision",
        final_decision,
        "--confirm-refinement-finalization",
        "--json",
    )

    final_project = ResearchProject.open(project.root)
    baseline_after = immutable_stage_twelve_snapshot(final_project)
    recorded_selection = json.loads(
        (project.root / "refinement/final_selection.json").read_text(encoding="utf-8")
    )
    no_network_or_llm_client_was_called = not llm_client_calls
    assert final_project.state.current_stage == 14
    assert baseline_after == baseline_before
    assert candidate_manifest.startswith(".researchclaw/evidence/refinement-manifests/")
    assert recorded_selection["dissenting_roles"] == ["critical_reproducibility"]
    assert no_network_or_llm_client_was_called
