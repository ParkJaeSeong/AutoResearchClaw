"""Synthetic public-CLI proof of the Stage 13 council workflow."""

import json
import os
import shlex
import subprocess
from pathlib import Path

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
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


ROOT = Path(__file__).parents[2]
REFINEMENT_REFERENCE = ROOT / "skills" / "researchclaw" / "references" / "refinement.md"
VOTING_ROLES = ("domain", "methodology", "critical_reproducibility")
NETWORK_GUARD_ROOT = Path(__file__).parent / "fixtures" / "stage13_network_guard"


def _write_record(project, relative_path, payload):
    path = project.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return relative_path


def _run_json(capsys, *argv):
    assert main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def _guarded_subprocess(argv, *, cwd, attempts_path, probe=None):
    environment = dict(os.environ)
    inherited_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(NETWORK_GUARD_ROOT), str(ROOT), inherited_path) if part
    )
    environment["RESEARCHCLAW_STAGE13_NETWORK_GUARD_LOG"] = str(attempts_path)
    if probe is not None:
        environment["RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE"] = probe
    return subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=1,
    )


def _assert_blocked_probe(argv, *, cwd, attempts_path, probe, event):
    attempted = _guarded_subprocess(
        argv,
        cwd=cwd,
        attempts_path=attempts_path,
        probe=probe,
    )
    assert attempted.returncode != 0
    assert set(attempts_path.read_text(encoding="utf-8").splitlines()) == {
        f"{probe}:{event}"
    }
    attempts_path.write_text("", encoding="utf-8")


def _expected_candidate_metric(project, run):
    context = json.loads(
        (project.root / run["contract_path"]).read_text(encoding="utf-8")
    )
    config = json.loads(
        (Path(run["cwd"]) / "config/config.json").read_text(encoding="utf-8")
    )
    input_total = sum(
        sum(Path(binding["absolute_path"]).read_bytes())
        for binding in context["execution"]["input_bindings"]
    )
    return (sum(config["seeds"]["values"]) + input_total / 1000.0) / len(
        config["seeds"]["values"]
    )


def test_public_e2e_subprocess_has_one_second_hard_timeout(tmp_path, monkeypatch):
    observed = {}

    def record_run(argv, **kwargs):
        observed.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record_run)

    _guarded_subprocess(
        ("trusted-launcher", "candidate-entrypoint"),
        cwd=tmp_path,
        attempts_path=tmp_path / "attempts.log",
    )

    assert observed["timeout"] == 1


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
    tmp_path, capsys
):
    """Exercise the documented user-mediated protocol through public subprocess argv."""
    # The public user entry must exist before this synthetic workflow is usable.
    assert "researchclaw-codex refinement" in REFINEMENT_REFERENCE.read_text().lower()

    project = build_stage_thirteen_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    e2e_envelope = valid_envelope()
    e2e_envelope["maximum_candidate_seconds"] = 1
    envelope = _write_record(project, "refinement/envelope.json", e2e_envelope)
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
    network_attempts = tmp_path / "subprocess-network-attempts.log"
    network_attempts.write_text("", encoding="utf-8")
    completed = _guarded_subprocess(
        self_test["argv"],
        cwd=self_test["cwd"],
        attempts_path=network_attempts,
    )
    assert completed.returncode == 0, completed.stderr
    assert network_attempts.read_text(encoding="utf-8") == ""
    for probe, event in (
        ("tcp", "socket.connect"),
        ("sockettype_sendmsg", "socket.sendmsg"),
        ("bind", "socket.bind"),
        ("create_server", "socket.create_server"),
        ("create_connection", "socket.create_connection"),
        ("sendto", "socket.sendto"),
        ("sendto_flags", "socket.sendto"),
        ("sendmsg", "socket.sendmsg"),
        ("send", "socket.send"),
        ("sendall", "socket.sendall"),
        ("connect_ex", "socket.connect_ex"),
        ("sendfile", "socket.sendfile"),
        ("getaddrinfo", "socket.getaddrinfo"),
        ("dns_name", "socket.gethostbyname"),
        ("dns_name_ex", "socket.gethostbyname_ex"),
        ("dns_addr", "socket.gethostbyaddr"),
        ("provider", "socket.create_connection"),
    ):
        _assert_blocked_probe(
            self_test["argv"],
            cwd=self_test["cwd"],
            attempts_path=network_attempts,
            probe=probe,
            event=event,
        )
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
    run_contract = json.loads(
        (project.root / run["contract_path"]).read_text(encoding="utf-8")
    )
    assert run_contract["envelope"]["reserved_maximum_seconds"] == 1
    completed = _guarded_subprocess(
        run["argv"],
        cwd=run["cwd"],
        attempts_path=network_attempts,
    )
    assert completed.returncode == 0, completed.stderr
    assert network_attempts.read_text(encoding="utf-8") == ""
    produced_result = json.loads(
        (project.root / run["result_path"]).read_text(encoding="utf-8")
    )
    assert produced_result["metrics"]["primary"]["value"] == _expected_candidate_metric(
        project, run
    )
    assert produced_result["runtime"]["maximum_seconds"] == 1
    assert 0.0 < produced_result["runtime"]["elapsed_seconds"] <= 1
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
    assert 0.0 < candidate_result["wall_seconds_used"] <= 1
    # This negative guard probe is independent of the approved one-second run.
    # Perform it after acceptance so it cannot consume the registration budget.
    registered_result_bytes = (project.root / run["result_path"]).read_bytes()
    _assert_blocked_probe(
        run["argv"],
        cwd=run["cwd"],
        attempts_path=network_attempts,
        probe="provider",
        event="socket.create_connection",
    )
    assert (project.root / run["result_path"]).read_bytes() == registered_result_bytes

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
    assert final_project.state.current_stage == 14
    assert baseline_after == baseline_before
    assert candidate_manifest.startswith(".researchclaw/evidence/refinement-manifests/")
    assert recorded_selection["dissenting_roles"] == ["critical_reproducibility"]
    handoff = _run_json(capsys, "resume", str(project.root), "--json")
    assert handoff["stage_name"] == "result_analysis"
    assert handoff["next_action"] == "await_stage_fourteen_support"
    assert handoff["write_policy"] == "read_only"
    assert handoff["milestone_complete"] is False
    status_command = _guarded_subprocess(
        shlex.split(handoff["next_command"]), cwd=ROOT,
        attempts_path=network_attempts,
    )
    assert status_command.returncode == 0, status_command.stderr
    status = json.loads(status_command.stdout)
    assert status["current_stage"] == 14
    assert status["boundary_message"] == handoff["boundary_message"]
    assert "future" in status["boundary_message"]
    assert ResearchProject.open(project.root).state == final_project.state
    assert network_attempts.read_text(encoding="utf-8") == ""
