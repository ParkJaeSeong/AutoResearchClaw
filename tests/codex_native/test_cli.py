import hashlib
import json
import os
from pathlib import Path
import shlex
import secrets
import subprocess
import sys
from types import SimpleNamespace
from dataclasses import replace

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
from researchclaw.core.models import ArtifactRef
from researchclaw.core.refinement import CandidateStatus, RefinementSessionStatus
from researchclaw.core.experiment_package_contract import validate_experiment_package_contract
from researchclaw.core.research_execution import prepare_research_execution
from researchclaw.core.research_execution import register_research_result
from researchclaw.core import evidence_store
from researchclaw.core import evidence_registration
from researchclaw.core.evidence_store import quarantine_unregistered_result
from researchclaw.core.events import EventLog, event_log_for
from researchclaw.core.state import StateStore
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    build_self_test_registration_project,
    build_completed_validation_design_project,
    build_stage_thirteen_project,
    build_stage_twelve_project,
    load_execution_contract,
    write_runnable_development_fixture,
    write_contract_bound_research_result,
)
from tests.codex_native.test_refinement import (
    valid_assessment_record,
    valid_decision_record,
    valid_envelope,
    valid_rebuttals_record,
    write_refinement_candidate,
)
from tests.codex_native.test_refinement_execution import write_refinement_result


def test_refinement_prepare_session_cli_is_agent_neutral(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    envelope = project.root / "refinement" / "envelope.json"
    envelope.parent.mkdir(parents=True)
    envelope.write_text(json.dumps(valid_envelope()), encoding="utf-8")

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["phase"] == "awaiting_independent_assessments"
    assert "model" not in payload and "api_key" not in payload


def _write_refinement_cli_record(project, relative_path, payload):
    path = project.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return relative_path


def _prepare_refinement_session_with_cli(project, capsys):
    envelope = _write_refinement_cli_record(
        project, "refinement/envelope.json", valid_envelope()
    )
    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", envelope, "--json",
    ]) == 0
    capsys.readouterr()


def _register_refinement_assessments_with_cli(project, capsys):
    for role in ("domain", "methodology", "critical_reproducibility"):
        assessment = _write_refinement_cli_record(
            project,
            f"submissions/{role}.json",
            valid_assessment_record(project, role=role),
        )
        assert main([
            "refinement", "register-assessment", str(project.root),
            "--assessment", assessment, "--json",
        ]) == 0
        capsys.readouterr()
    rebuttals = _write_refinement_cli_record(
        project, "submissions/rebuttals.json", valid_rebuttals_record(project)
    )
    assert main([
        "refinement", "register-deliberation", str(project.root),
        "--rebuttals", rebuttals, "--json",
    ]) == 0
    capsys.readouterr()


def _register_refinement_decision_with_cli(project, capsys, payload):
    decision = _write_refinement_cli_record(project, "submissions/decision.json", payload)
    assert main([
        "refinement", "register-decision", str(project.root),
        "--decision", decision, "--json",
    ]) == 0
    capsys.readouterr()
    return decision


def test_refinement_cli_dispatches_registration_self_test_run_and_status(
    tmp_path, capsys
):
    project = build_stage_thirteen_project(tmp_path / "project")
    _prepare_refinement_session_with_cli(project, capsys)
    _register_refinement_assessments_with_cli(project, capsys)
    _register_refinement_decision_with_cli(project, capsys, valid_decision_record(project))

    manifest = write_refinement_candidate(project)
    assert main([
        "refinement", "register-candidate", str(project.root),
        "--manifest", str(manifest.relative_to(project.root)), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["candidate_id"] == "candidate-001"

    assert main([
        "refinement", "prepare-self-test", str(project.root),
        "--candidate-id", "candidate-001", "--json",
    ]) == 0
    self_test = json.loads(capsys.readouterr().out)
    completed = subprocess.run(
        self_test["argv"], cwd=self_test["cwd"], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr

    assert main([
        "refinement", "register-self-test", str(project.root),
        "--candidate-id", "candidate-001", "--report", self_test["report_path"],
        "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_self_test_confirmation_required\n"
    assert ResearchProject.open(project.root).state.next_action == "prepare_refinement_self_test"

    assert main([
        "refinement", "register-self-test", str(project.root),
        "--candidate-id", "candidate-001", "--report", self_test["report_path"],
        "--confirm-refinement-self-test", "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["next_action"] == "prepare_refinement_run"

    assert main([
        "refinement", "prepare-run", str(project.root),
        "--candidate-id", "candidate-001", "--json",
    ]) == 0
    run = json.loads(capsys.readouterr().out)
    write_refinement_result(project, SimpleNamespace(**run))

    assert main([
        "refinement", "register-result", str(project.root),
        "--candidate-id", "candidate-001", "--result", run["result_path"], "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_result_confirmation_required\n"
    assert ResearchProject.open(project.root).state.next_action == "register_refinement_result"

    assert main([
        "refinement", "register-result", str(project.root),
        "--candidate-id", "candidate-001", "--result", run["result_path"],
        "--confirm-refinement-result", "--json",
    ]) == 0
    capsys.readouterr()

    assert main(["refinement", "status", str(project.root), "--json"]) == 0
    encoded = capsys.readouterr().out
    status = json.loads(encoded)
    assert status["phase"] == "awaiting_independent_assessments"
    assert encoded == json.dumps(status, ensure_ascii=False, sort_keys=True) + "\n"


def test_refinement_cli_finalization_requires_confirmation_without_mutation(
    tmp_path, capsys
):
    project = build_stage_thirteen_project(tmp_path / "project")
    _prepare_refinement_session_with_cli(project, capsys)
    _register_refinement_assessments_with_cli(project, capsys)
    final_decision = valid_decision_record(
        project,
        votes=("retain_baseline", "retain_baseline", "inconclusive"),
    )
    final_decision["action"] = "retain_baseline"
    final_decision["candidate_id"] = None
    final_decision["supporting_roles"] = ["domain", "methodology"]
    final_decision["dissenting_roles"] = ["critical_reproducibility"]
    final_decision["rationale"] = ["The evidence supports retaining the baseline."]
    final_decision["limitations"] = ["The result remains limited to registered inputs."]
    final_decision["stage_14_questions"] = ["Does the conclusion survive sensitivity analysis?"]
    final_decision.pop("change_request")
    decision = _register_refinement_decision_with_cli(project, capsys, final_decision)

    assert main([
        "refinement", "finalize", str(project.root), "--decision", decision, "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_finalization_confirmation_required\n"
    assert ResearchProject.open(project.root).state.current_stage == 13

    assert main([
        "refinement", "finalize", str(project.root), "--decision", decision,
        "--confirm-refinement-finalization", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["phase"] == "completed"
    assert ResearchProject.open(project.root).state.current_stage == 14


def test_refinement_cli_rejects_unsafe_paths_and_agent_controls_without_mutation(
    tmp_path, capsys
):
    project = build_stage_thirteen_project(tmp_path / "project")

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "../outside.json", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_path_invalid\n"
    assert not (project.root / "refinement/session.json").exists()

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--model", "untrusted", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_argument_invalid\n"


def test_refinement_prepare_session_rejects_duplicate_envelope_keys(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    envelope = project.root / "refinement" / "envelope.json"
    envelope.parent.mkdir(parents=True)
    envelope.write_text(
        json.dumps(valid_envelope()).replace(
            '{"schema_version": 1,', '{"schema_version": 1, "schema_version": 1,'
        ),
        encoding="utf-8",
    )

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_envelope_invalid\n"
    assert not (project.root / "refinement/session.json").exists()


@pytest.mark.parametrize(
    "contents",
    (
        "[" * 2_000 + "0" + "]" * 2_000,
        '{"maximum_runs":' + "9" * 5_000 + "}",
    ),
)
def test_refinement_prepare_session_rejects_pathological_envelopes(
    tmp_path, capsys, contents
):
    project = build_stage_thirteen_project(tmp_path / "project")
    envelope = project.root / "refinement" / "envelope.json"
    envelope.parent.mkdir(parents=True)
    envelope.write_text(contents, encoding="utf-8")

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_envelope_invalid\n"
    assert not (project.root / "refinement/session.json").exists()


def test_refinement_prepare_session_rejects_fifo_envelope(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    envelope = project.root / "refinement" / "envelope.json"
    envelope.parent.mkdir(parents=True)
    os.mkfifo(envelope)

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_envelope_invalid\n"
    assert not (project.root / "refinement/session.json").exists()


def test_refinement_cli_preserves_stable_core_validation_codes(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    envelope = project.root / "refinement" / "envelope.json"
    envelope.parent.mkdir(parents=True)
    envelope.write_text("{}", encoding="utf-8")

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_envelope_schema_invalid\n"


def test_refinement_cli_sanitizes_newline_bearing_paths(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")

    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "../outside\nerror: injected", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_path_invalid\n"
    assert not (project.root / "refinement/session.json").exists()


def test_refinement_statuses_expose_closed_public_json_contracts():
    session = RefinementSessionStatus(
        session_id="session-001",
        phase="awaiting_candidate",
        evidence_packet_path="refinement/evidence_packet.json",
        evidence_packet_sha256="a" * 64,
        runs_used=1,
        maximum_runs=2,
        next_action="register_refinement_candidate",
        wall_seconds_used=1.5,
    )
    candidate = CandidateStatus(
        candidate_id="candidate-001",
        manifest_path="refinement/candidates/candidate-001/package_metadata/manifest.json",
        manifest_sha256="b" * 64,
        decision_sha256="c" * 64,
        package_contract_sha256="d" * 64,
        entry_point="code/model.py",
        files=(ArtifactRef("refinement/candidates/candidate-001/code/model.py", "e" * 64, 12),),
        next_action="prepare_refinement_self_test",
    )

    assert session.to_dict() == {
        "session_id": "session-001",
        "phase": "awaiting_candidate",
        "evidence_packet_path": "refinement/evidence_packet.json",
        "evidence_packet_sha256": "a" * 64,
        "runs_used": 1,
        "maximum_runs": 2,
        "next_action": "register_refinement_candidate",
        "wall_seconds_used": 1.5,
    }
    assert candidate.to_dict() == {
        "candidate_id": "candidate-001",
        "manifest_path": "refinement/candidates/candidate-001/package_metadata/manifest.json",
        "manifest_sha256": "b" * 64,
        "decision_sha256": "c" * 64,
        "package_contract_sha256": "d" * 64,
        "entry_point": "code/model.py",
        "files": [{
            "path": "refinement/candidates/candidate-001/code/model.py",
            "sha256": "e" * 64,
            "size": 12,
        }],
        "next_action": "prepare_refinement_self_test",
    }


def test_refinement_cli_rejects_abbreviated_confirmation_options(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")

    assert main([
        "refinement", "register-self-test", str(project.root),
        "--candidate-id", "candidate-001", "--report", "report.json", "--confirm", "--json",
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_argument_invalid\n"


def test_refinement_status_rejects_deeply_nested_project_state(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    state_path = project.root / ".researchclaw" / "state.json"
    nested_state = "[" * 2_000 + "]" * 2_000
    state_path.write_text(nested_state, encoding="utf-8")

    assert main(["refinement", "status", str(project.root), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: refinement_project_invalid\n"
    assert state_path.read_text(encoding="utf-8") == nested_state


def test_refinement_status_returns_normal_session_payload(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    _prepare_refinement_session_with_cli(project, capsys)

    assert main(["refinement", "status", str(project.root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["phase"] == "awaiting_independent_assessments"
    assert payload["next_action"] == "register_refinement_assessment"


def _run_known_answer_self_test(project):
    package = validate_experiment_package_contract(project)
    result = subprocess.run(
        [sys.executable, "experiment/code/main.py", *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _remove_stage_ten_snapshot(project):
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.pop("stage_10_snapshot", None)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def test_init_then_status_outputs_machine_readable_json(tmp_path, capsys):
    root = tmp_path / "demo"

    assert main(["init", str(root), "--topic", "Formation energy", "--profile", "materials_ai", "--json"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["status"] == "ready"

    assert main(["status", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_stage"] == 1
    assert payload["status"] == "ready"


def test_json_errors_keep_stdout_empty(tmp_path, capsys):
    exit_code = main(["status", str(tmp_path / "missing"), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "state.json" in captured.err


def test_quarantine_result_cli_requires_confirmation_and_moves_regular_result(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)

    assert main(
        [
            "execution", "quarantine-result", str(project.root),
            "--reason", "invalid_result", "--json",
        ]
    ) == 2
    assert not capsys.readouterr().out

    assert main(
        [
            "execution", "quarantine-result", str(project.root),
            "--reason", "invalid_result", "--confirm", "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["original_path"] == "experiment/results.json"
    assert payload["reason"] == "invalid_result"
    assert (project.root / "experiment/results.json").is_file()
    assert (project.root / payload["quarantine_path"]).is_file()
    handoff = ResearchProject.open(project.root).build_handoff()
    assert handoff.next_action == "cleanup_quarantined_result"
    assert "cleanup-quarantined-result" in handoff.next_command
    assert main(
        [
            "execution", "cleanup-quarantined-result", str(project.root),
            "--json",
        ]
    ) == 2
    capsys.readouterr()
    assert main(
        [
            "execution", "cleanup-quarantined-result", str(project.root),
            "--confirm", "--json",
        ]
    ) == 0
    cleanup = json.loads(capsys.readouterr().out)
    assert cleanup["cleaned_path"] == "experiment/results.json"
    assert (project.root / cleanup["preserved_path"]).is_file()
    assert not (project.root / "experiment/results.json").exists()
    assert ResearchProject.open(project.root).build_handoff().next_action == "prepare_run"
    prepared = prepare_research_execution(ResearchProject.open(project.root))
    completed = subprocess.run(
        prepared.argv,
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    registered = register_research_result(
        ResearchProject.open(project.root), "experiment/results.json"
    )
    assert registered.current_stage == 13
    assert registered.manifest_path.startswith(".researchclaw/evidence/manifests/")


@pytest.mark.parametrize(
    "fault_seam",
    (
        "_after_result_quarantine_temp_created",
        "_after_result_quarantine_temp_write",
        "_after_result_quarantine_temp_fsync",
        "_after_result_quarantine_publish",
        "_after_result_quarantine_move",
        "_after_result_quarantine_event",
        "_after_result_quarantine_state",
    ),
)
def test_quarantine_result_recovers_each_durable_seam(
    tmp_path, monkeypatch, fault_seam
):
    project = build_approved_stage_twelve_project(tmp_path / fault_seam)
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    monkeypatch.setattr(
        evidence_store, fault_seam, lambda: (_ for _ in ()).throw(OSError("fault"))
    )
    with pytest.raises(OSError, match="fault"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    assert (project.root / result.quarantine_path).is_file()
    assert ResearchProject.open(project.root).state.next_action == "cleanup_quarantined_result"
    assert sum(
        event.type == "research_result_quarantined"
        for event in event_log_for(project.root).read_all()
    ) == 1


def test_quarantine_copies_captured_descriptor_without_moving_replacement(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    source = project.root / "experiment/results.json"
    original = project.root / "experiment/original-results.json"
    original_bytes = source.read_bytes()

    def replace_source():
        source.rename(original)
        source.write_bytes(b"unrelated replacement")

    monkeypatch.setattr(evidence_store, "_before_result_quarantine_move", replace_source)
    result = quarantine_unregistered_result(project, "invalid_result", True)

    assert source.read_bytes() == b"unrelated replacement"
    assert original.is_file()
    assert (project.root / result.quarantine_path).read_bytes() == original_bytes


def test_quarantine_late_hardlink_only_copies_validated_descriptor_bytes(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    source = project.root / "experiment/results.json"
    payload = source.read_bytes()
    external_link = project.root / "experiment/late-link.json"

    monkeypatch.setattr(
        evidence_store,
        "_before_result_quarantine_move",
        lambda: os.link(source, external_link),
    )
    result = quarantine_unregistered_result(project, "invalid_result", True)

    assert source.read_bytes() == payload
    assert external_link.read_bytes() == payload
    assert (project.root / result.quarantine_path).read_bytes() == payload


def test_quarantine_rejects_result_referenced_by_noncurrent_valid_manifest(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    register_research_result(project, "experiment/results.json")
    current = ResearchProject.open(project.root).state
    StateStore(project.root / ".researchclaw").save(
        replace(
            current,
            current_stage=12,
            completed_stages=tuple(stage for stage in current.completed_stages if stage != 12),
            next_action="prepare_run",
            artifacts={
                path: ref
                for path, ref in current.artifacts.items()
                if not path.startswith(".researchclaw/evidence/")
            },
        )
    )

    with pytest.raises(ValueError, match="registered evidence"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )


def test_quarantine_repairs_owned_partial_event_before_retry(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    def partial_append(self, event, *, expected_offset):
        record = EventLog._bounded_record(event)
        with self.path.open("ab") as handle:
            handle.write(record[:8])
            handle.flush()
            os.fsync(handle.fileno())
        raise OSError("partial event")

    monkeypatch.setattr(EventLog, "append_locked", partial_append)
    with pytest.raises(OSError, match="partial event"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    quarantine_unregistered_result(project, "invalid_result", True)
    assert sum(
        event.type == "research_result_quarantined"
        for event in event_log_for(project.root).read_all()
    ) == 1


def test_quarantine_event_recovery_never_scans_huge_prior_log(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    log = event_log_for(project.root)
    for index in range(64):
        log.append(
            evidence_store.EvaluationEvent.create(
                "large_prior_event",
                project.state.project_id,
                {"index": index, "padding": "x" * 4096},
            )
        )
    monkeypatch.setattr(
        EventLog,
        "read_all",
        lambda _self: (_ for _ in ()).throw(AssertionError("unbounded scan")),
    )

    result = quarantine_unregistered_result(project, "invalid_result", True)

    assert (project.root / result.quarantine_path).is_file()


def test_quarantine_event_recovery_preserves_foreign_tail(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    def foreign_append(self, _event, *, expected_offset):
        with self.path.open("ab") as handle:
            handle.write(b"foreign-tail")
            handle.flush()
            os.fsync(handle.fileno())
        raise OSError("foreign event")

    monkeypatch.setattr(EventLog, "append_locked", foreign_append)
    with pytest.raises(OSError, match="foreign event"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    with pytest.raises(ValueError, match="result_quarantine_interrupted"):
        quarantine_unregistered_result(project, "invalid_result", True)
    assert (project.root / "evaluation/events.jsonl").read_bytes().endswith(
        b"foreign-tail"
    )


def test_quarantine_event_identity_is_bound_to_reserved_offset(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    event = evidence_store.EvaluationEvent.create(
        "research_result_quarantined",
        project.state.project_id,
        {
            "original_path": "experiment/results.json",
            "sha256": "0" * 64,
            "size": 0,
            "reason": "invalid_result",
            "quarantine_path": ".researchclaw/evidence/quarantine/results/prior.json",
        },
    )
    event_log_for(project.root).append(event)
    path = project.root / "evaluation/events.jsonl"
    reserved_offset = path.stat().st_size

    assert evidence_store._result_quarantine_event_at_offset(
        project, event, reserved_offset
    ) is False


def test_quarantine_resumes_partial_transaction_owned_temp(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    original_write = evidence_store._write_all
    failed = False

    def partial_write(descriptor, chunk):
        nonlocal failed
        if not failed:
            failed = True
            os.write(descriptor, chunk[:17])
            raise OSError("disk write fault")
        original_write(descriptor, chunk)

    monkeypatch.setattr(evidence_store, "_write_all", partial_write)
    with pytest.raises(OSError, match="disk write fault"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    assert (project.root / result.quarantine_path).is_file()


def test_quarantine_growth_probe_is_bounded_and_never_writes_extra_byte(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    source = project.root / "experiment/results.json"
    expected_size = source.stat().st_size
    source_identity = (source.stat().st_dev, source.stat().st_ino)
    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_created",
        lambda: (_ for _ in ()).throw(OSError("owned temp")),
    )
    with pytest.raises(OSError, match="owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    real_read = os.read
    source_read_bytes = 0

    def bounded_read(descriptor, size):
        nonlocal source_read_bytes
        chunk = real_read(descriptor, size)
        file_stat = os.fstat(descriptor)
        if (file_stat.st_dev, file_stat.st_ino) == source_identity:
            source_read_bytes += len(chunk)
        return chunk

    def append_huge_tail():
        with source.open("ab") as stream:
            stream.write(b"x" * (8 * 1024 * 1024))

    monkeypatch.setattr(os, "read", bounded_read)
    monkeypatch.setattr(
        evidence_store, "_before_result_quarantine_growth_probe", append_huge_tail
    )
    with pytest.raises(ValueError, match="source changed"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    assert temporary.stat().st_size == expected_size
    assert source_read_bytes == expected_size + 1


def test_quarantine_complete_owned_temp_publishes_read_only_at_capacity_boundary(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "complete")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_fsync",
        lambda: (_ for _ in ()).throw(OSError("complete owned temp")),
    )
    with pytest.raises(OSError, match="owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    expected_size = pending["size"]
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    before_identity = (temporary.stat().st_dev, temporary.stat().st_ino)
    remaining = expected_size - temporary.stat().st_size
    monkeypatch.setattr(evidence_store, "_RESULT_QUARANTINE_ENTRY_LIMIT", 1)
    monkeypatch.setattr(evidence_store, "_RESULT_QUARANTINE_BYTE_LIMIT", expected_size)
    monkeypatch.setattr(
        os,
        "fstatvfs",
        lambda _descriptor: SimpleNamespace(f_bavail=remaining, f_frsize=1),
    )

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )

    destination = project.root / result.quarantine_path
    assert (destination.stat().st_dev, destination.stat().st_ino) == before_identity
    assert destination.stat().st_size == expected_size


def test_quarantine_partial_owned_temp_is_never_resumed_after_late_hardlink(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "late-hardlink")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_write = evidence_store._write_all
    failed = False

    def partial_write(descriptor, chunk):
        nonlocal failed
        if not failed:
            failed = True
            os.write(descriptor, chunk[:17])
            raise OSError("partial owned temp")
        real_write(descriptor, chunk)

    monkeypatch.setattr(evidence_store, "_write_all", partial_write)
    with pytest.raises(OSError, match="partial owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    before = temporary.read_bytes()
    external_link = tmp_path / "late-hardlink.bin"

    def add_late_hardlink():
        os.link(temporary, external_link)

    monkeypatch.setattr(
        evidence_store, "_after_result_quarantine_temp_reopen_validation", add_late_hardlink
    )
    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )

    assert temporary.read_bytes() == before
    assert external_link.read_bytes() == before
    assert (project.root / result.quarantine_path).read_bytes() != before
    assert (project.root / result.quarantine_path).stat().st_ino != temporary.stat().st_ino


def test_quarantine_partial_owned_temp_at_capacity_fails_without_mutation(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "partial-at-capacity")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_write = evidence_store._write_all
    failed = False

    def partial_write(descriptor, chunk):
        nonlocal failed
        if not failed:
            failed = True
            os.write(descriptor, chunk[:17])
            raise OSError("partial owned temp")
        real_write(descriptor, chunk)

    monkeypatch.setattr(evidence_store, "_write_all", partial_write)
    with pytest.raises(OSError, match="partial owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    before = temporary.read_bytes()
    monkeypatch.setattr(evidence_store, "_RESULT_QUARANTINE_ENTRY_LIMIT", 1)

    with pytest.raises(
        evidence_store.ResultQuarantineCapacityError,
        match="operator cleanup|required|capacity",
    ):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    assert temporary.read_bytes() == before


@pytest.mark.parametrize("mutation", ("append", "replace"))
def test_quarantine_owned_temp_source_drift_and_path_replacement_fail_closed(
    tmp_path, monkeypatch, mutation
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_created",
        lambda: (_ for _ in ()).throw(OSError("owned temp")),
    )
    with pytest.raises(OSError, match="owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    original_temp = temporary.read_bytes()
    source = project.root / "experiment/results.json"
    if mutation == "append":
        with source.open("ab") as stream:
            stream.write(b"drift")
    else:
        source.rename(project.root / "experiment/original-results.json")
        source.write_bytes(b'{"replacement":true}\n')

    with pytest.raises(ValueError, match="source changed"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    assert temporary.read_bytes() == original_temp


def test_quarantine_owned_temp_prefix_drift_is_preserved_and_refused(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_write = evidence_store._write_all
    failed = False

    def partial_write(descriptor, chunk):
        nonlocal failed
        if not failed:
            failed = True
            os.write(descriptor, chunk[:17])
            raise OSError("partial owned temp")
        real_write(descriptor, chunk)

    monkeypatch.setattr(evidence_store, "_write_all", partial_write)
    with pytest.raises(OSError, match="partial owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    with temporary.open("r+b") as stream:
        stream.write(b"X")
    changed = temporary.read_bytes()

    with pytest.raises(ValueError, match="temporary collision"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    assert temporary.read_bytes() == changed


def test_quarantine_owned_temp_identity_replacement_is_preserved_and_refused(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_created",
        lambda: (_ for _ in ()).throw(OSError("owned temp")),
    )
    with pytest.raises(OSError, match="owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    temporary.unlink()
    temporary.write_bytes(b"foreign replacement")

    with pytest.raises(ValueError, match="temporary collision"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    assert temporary.read_bytes() == b"foreign replacement"


def test_quarantine_owned_partial_late_path_replacement_is_preserved_and_rotated(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_write = evidence_store._write_all
    failed = False

    def partial_write(descriptor, chunk):
        nonlocal failed
        if not failed:
            failed = True
            os.write(descriptor, chunk[:17])
            raise OSError("partial owned temp")
        real_write(descriptor, chunk)

    monkeypatch.setattr(evidence_store, "_write_all", partial_write)
    with pytest.raises(OSError, match="partial owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    original = temporary.with_name("owned-original-preserved.tmp")
    original_bytes = temporary.read_bytes()
    foreign = b"late foreign replacement"

    def replace_after_reopen():
        temporary.rename(original)
        temporary.write_bytes(foreign)

    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_reopen_validation",
        replace_after_reopen,
    )
    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )

    assert temporary.read_bytes() == foreign
    assert original.read_bytes() == original_bytes
    assert (project.root / result.quarantine_path).stat().st_ino != original.stat().st_ino


@pytest.mark.parametrize("tamper", ("hardlink", "oversize", "symlink"))
def test_quarantine_owned_temp_rejects_topology_or_size_tamper(
    tmp_path, monkeypatch, tamper
):
    project = build_approved_stage_twelve_project(tmp_path / tamper)
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_created",
        lambda: (_ for _ in ()).throw(OSError("owned temp")),
    )
    with pytest.raises(OSError, match="owned temp"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    temporary = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    if tamper == "hardlink":
        os.link(temporary, project.root / "experiment/temp-hardlink")
    elif tamper == "oversize":
        temporary.write_bytes(b"x" * (pending["size"] + 1))
    else:
        temporary.unlink()
        temporary.symlink_to(project.root / "experiment/results.json")

    with pytest.raises(ValueError, match="temporary collision"):
        quarantine_unregistered_result(
            ResearchProject.open(project.root), "invalid_result", True
        )

    if tamper == "symlink":
        assert temporary.is_symlink()
    else:
        assert temporary.exists()


def test_quarantine_recovers_temp_fsync_disk_error_after_reopen(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_fsync = os.fsync
    armed = False

    def arm_fsync_fault():
        nonlocal armed
        armed = True

    def fail_one_fsync(descriptor):
        nonlocal armed
        if armed:
            armed = False
            raise OSError("fsync disk fault")
        real_fsync(descriptor)

    monkeypatch.setattr(evidence_store, "_after_result_quarantine_temp_write", arm_fsync_fault)
    monkeypatch.setattr(os, "fsync", fail_one_fsync)
    with pytest.raises(OSError, match="fsync disk fault"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    assert (project.root / result.quarantine_path).is_file()


def test_quarantine_recovers_native_publish_error_after_reopen(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    real_publish = evidence_store._native_rename_noreplace
    failed = False

    def fail_one_publish(*args):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("publish disk fault")
        return real_publish(*args)

    monkeypatch.setattr(evidence_store, "_native_rename_noreplace", fail_one_publish)
    with pytest.raises(OSError, match="publish disk fault"):
        quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.undo()

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    assert (project.root / result.quarantine_path).is_file()


def test_quarantine_rotates_unknown_temp_after_create_identity_gap(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    monkeypatch.setattr(
        evidence_store,
        "_after_result_quarantine_temp_open",
        lambda: (_ for _ in ()).throw(OSError("create identity gap")),
    )
    with pytest.raises(OSError, match="create identity gap"):
        quarantine_unregistered_result(project, "invalid_result", True)
    pending = json.loads(
        (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text()
    )
    abandoned = (
        project.root / ".researchclaw/evidence/quarantine/copies"
        / pending["temporary_name"]
    )
    source_prefix = (project.root / "experiment/results.json").read_bytes()[:17]
    abandoned.write_bytes(source_prefix)
    monkeypatch.undo()

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    assert (project.root / result.quarantine_path).is_file()
    assert abandoned.read_bytes() == source_prefix
    inventory = evidence_store.result_quarantine_inventory(project)
    assert abandoned.relative_to(project.root).as_posix() in inventory.abandoned_paths


def test_quarantine_unknown_temp_rotation_is_bounded(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    evidence_store.EvidenceStore(project.root)
    copies = project.root / ".researchclaw/evidence/quarantine/copies"
    collision = ".copy-" + "a" * 32 + ".tmp"
    (copies / collision).write_bytes(b"foreign")
    pending_path = project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH

    def collide_before_create():
        pending = json.loads(pending_path.read_text())
        if pending["temporary_device"] == 0:
            candidate = copies / pending["temporary_name"]
            if not candidate.exists():
                candidate.write_bytes(b"foreign")

    monkeypatch.setattr(secrets, "token_hex", lambda _size: "a" * 32)
    monkeypatch.setattr(
        evidence_store, "_before_result_quarantine_move", collide_before_create
    )
    with pytest.raises(ValueError, match="operator cleanup required"):
        quarantine_unregistered_result(project, "invalid_result", True)

    assert (copies / collision).read_bytes() == b"foreign"


def test_quarantine_repeated_identity_gap_crashes_preserve_inventory(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    remaining = 3

    def fail_three_creates():
        nonlocal remaining
        if remaining:
            remaining -= 1
            raise OSError("repeated create gap")

    monkeypatch.setattr(
        evidence_store, "_after_result_quarantine_temp_open", fail_three_creates
    )
    for _ in range(3):
        with pytest.raises(OSError, match="repeated create gap"):
            quarantine_unregistered_result(
                ResearchProject.open(project.root), "invalid_result", True
            )

    result = quarantine_unregistered_result(
        ResearchProject.open(project.root), "invalid_result", True
    )
    inventory = evidence_store.result_quarantine_inventory(project)
    assert (project.root / result.quarantine_path).is_file()
    assert len(inventory.abandoned_paths) == 3
    assert all((project.root / path).is_file() for path in inventory.abandoned_paths)


def test_quarantine_capacity_entry_boundary_fails_before_pending_mutation(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    store = evidence_store.EvidenceStore(project.root)
    (store.copy_quarantine_root / "foreign.bin").write_bytes(b"foreign")
    monkeypatch.setattr(evidence_store, "_RESULT_QUARANTINE_ENTRY_LIMIT", 1)

    with pytest.raises(ValueError, match="operator cleanup required"):
        quarantine_unregistered_result(project, "invalid_result", True)

    assert not (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).exists()
    assert (store.copy_quarantine_root / "foreign.bin").read_bytes() == b"foreign"


def test_quarantine_inventory_reports_bounded_truncation(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    store = evidence_store.EvidenceStore(project.root)
    for index in range(4):
        (store.results_quarantine_root / f"foreign-{index}.bin").write_bytes(b"x")
    monkeypatch.setattr(evidence_store, "_RESULT_QUARANTINE_ENTRY_LIMIT", 2)

    inventory = evidence_store.result_quarantine_inventory(project)

    assert inventory.truncated is True
    assert inventory.entry_count == 3
    assert len(inventory.result_paths) == 2
    assert inventory.operator_cleanup_required is True


def test_quarantine_enospc_preflight_fails_before_pending_mutation(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        os,
        "fstatvfs",
        lambda _descriptor: SimpleNamespace(f_bavail=0, f_frsize=4096),
    )

    with pytest.raises(ValueError, match="operator cleanup required"):
        quarantine_unregistered_result(project, "invalid_result", True)

    assert not (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).exists()


def test_quarantine_capacity_cli_error_is_structured_and_actionable(
    tmp_path, monkeypatch, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    monkeypatch.setattr(
        os,
        "fstatvfs",
        lambda _descriptor: SimpleNamespace(f_bavail=0, f_frsize=4096),
    )

    assert main(
        [
            "execution", "quarantine-result", str(project.root),
            "--reason", "invalid_result", "--confirm", "--json",
        ]
    ) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "result_quarantine_capacity"
    assert error["operator_cleanup_required"] is True
    assert error["inventory"]["available_bytes"] == 0
    assert error["inventory"]["operator_cleanup_required"] is True


@pytest.mark.parametrize(
    "metadata",
    (
        SimpleNamespace(f_bavail=True, f_frsize=4096),
        SimpleNamespace(f_bavail=1 << 62, f_frsize=4096),
    ),
)
def test_quarantine_inventory_rejects_boolean_or_overflow_capacity_metadata(
    tmp_path, monkeypatch, metadata
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    monkeypatch.setattr(os, "fstatvfs", lambda _descriptor: metadata)

    with pytest.raises(ValueError, match="capacity metadata is invalid"):
        evidence_store.result_quarantine_inventory(project)


def test_quarantine_inventory_retains_first_critical_capacity_measurement(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    calls = 0

    def changing_capacity(_descriptor):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            f_bavail=0 if calls == 1 else 1 << 30,
            f_frsize=4096,
        )

    monkeypatch.setattr(os, "fstatvfs", changing_capacity)
    inventory = evidence_store.result_quarantine_inventory(project)

    assert calls == 1
    assert inventory.available_bytes == 0
    assert inventory.operator_cleanup_required is True


def test_quarantine_inventory_and_operator_route_preserve_unsafe_entries(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    store = evidence_store.EvidenceStore(project.root)
    foreign = store.copy_quarantine_root / "foreign.bin"
    foreign.write_bytes(b"foreign")
    hardlink = store.copy_quarantine_root / "foreign-link.bin"
    os.link(foreign, hardlink)
    symlink = store.results_quarantine_root / "foreign-link"
    symlink.symlink_to(foreign)

    assert main(
        ["evidence", "quarantine-inventory", str(project.root), "--json"]
    ) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["operator_cleanup_required"] is True
    assert len(inventory["unsafe_paths"]) == 3
    assert main(
        ["evidence", "quarantine-operator-cleanup", str(project.root), "--json"]
    ) == 2
    capsys.readouterr()
    assert main(
        [
            "evidence", "quarantine-operator-cleanup", str(project.root),
            "--confirm", "--json",
        ]
    ) == 2
    status = json.loads(capsys.readouterr().out)
    assert status["reclaimed_bytes"] == 0
    assert status["manual_filesystem_action_required"] is True
    assert foreign.read_bytes() == b"foreign"
    assert hardlink.read_bytes() == b"foreign"
    assert symlink.is_symlink()


def test_cleanup_capacity_byte_cap_fails_before_source_move(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    quarantined = quarantine_unregistered_result(project, "invalid_result", True)
    monkeypatch.setattr(
        evidence_store, "_RESULT_QUARANTINE_BYTE_LIMIT", quarantined.size
    )

    with pytest.raises(ValueError, match="operator cleanup required"):
        evidence_store.cleanup_quarantined_result(project, True)

    assert (project.root / "experiment/results.json").is_file()
    assert ResearchProject.open(project.root).state.next_action == (
        "cleanup_quarantined_result"
    )


def test_quarantine_preserves_foreign_transaction_temp_collision(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    created = None

    def collide():
        nonlocal created
        pending = json.loads(
            (project.root / evidence_store.RESULT_QUARANTINE_PENDING_PATH).read_text(
                encoding="utf-8"
            )
        )
        created = (
            project.root / ".researchclaw/evidence/quarantine/copies"
            / pending["temporary_name"]
        )
        created.write_bytes(b"foreign temporary bytes")

    monkeypatch.setattr(evidence_store, "_before_result_quarantine_move", collide)
    result = quarantine_unregistered_result(project, "invalid_result", True)
    assert created is not None and created.read_bytes() == b"foreign temporary bytes"
    assert (project.root / result.quarantine_path).is_file()
    assert created.relative_to(project.root).as_posix() in (
        evidence_store.result_quarantine_inventory(project).abandoned_paths
    )


def test_cleanup_refuses_replacement_and_hardlink_ambiguity(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    quarantine_unregistered_result(project, "invalid_result", True)
    source = project.root / "experiment/results.json"
    external = project.root / "experiment/ambiguous-link.json"
    os.link(source, external)

    with pytest.raises(ValueError, match="cleanup source changed"):
        evidence_store.cleanup_quarantined_result(project, True)

    assert source.is_file()
    assert external.is_file()


def test_cleanup_restores_late_unrelated_path_replacement(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    quarantine_unregistered_result(project, "invalid_result", True)
    source = project.root / "experiment/results.json"
    captured = project.root / "experiment/captured-results.json"
    replacement = b'{"unrelated": true}\n'

    def replace_path():
        source.rename(captured)
        source.write_bytes(replacement)

    monkeypatch.setattr(evidence_store, "_before_result_cleanup_move", replace_path)
    with pytest.raises(ValueError, match="cleanup identity changed"):
        evidence_store.cleanup_quarantined_result(project, True)

    assert source.read_bytes() == replacement
    assert captured.is_file()
    assert ResearchProject.open(project.root).state.next_action == (
        "cleanup_quarantined_result"
    )


@pytest.mark.parametrize(
    "fault_seam", ("_after_result_cleanup_move", "_after_result_cleanup_state")
)
def test_cleanup_recovers_each_durable_seam(tmp_path, monkeypatch, fault_seam):
    project = build_approved_stage_twelve_project(tmp_path / fault_seam)
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    quarantine_unregistered_result(project, "invalid_result", True)

    monkeypatch.setattr(
        evidence_store, fault_seam, lambda: (_ for _ in ()).throw(OSError("fault"))
    )
    with pytest.raises(OSError, match="fault"):
        evidence_store.cleanup_quarantined_result(project, True)
    monkeypatch.undo()

    status = evidence_store.cleanup_quarantined_result(
        ResearchProject.open(project.root), True
    )
    assert status.next_action == "prepare_run"
    assert not (project.root / "experiment/results.json").exists()
    assert (project.root / status.preserved_path).is_file()


def test_quarantine_cleans_orphan_registration_anchor_before_copy(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    monkeypatch.setattr(
        evidence_registration,
        "_after_anchor_persisted",
        lambda: (_ for _ in ()).throw(OSError("anchor-only crash")),
    )
    with pytest.raises(OSError, match="anchor-only crash"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()
    anchor = project.root / evidence_registration.EVIDENCE_REGISTRATION_ANCHOR_PATH
    assert anchor.is_file()
    assert not (project.root / evidence_registration.EVIDENCE_PENDING_PATH).exists()
    with pytest.raises(ValueError, match="project_transaction_pending"):
        StateStore(project.root / ".researchclaw").save(project.state)

    result = quarantine_unregistered_result(project, "invalid_result", True)
    assert (project.root / result.quarantine_path).is_file()
    assert not anchor.exists()


def test_experiment_register_self_test_cli_records_external_report(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_known_answer_self_test(project)

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--confirm-self-test",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["path"] == "experiment/self_test_report.json"
    assert len(payload["sha256"]) == 64
    assert payload["size"] > 0
    assert captured.err == ""


def test_prepare_self_test_cli_returns_complete_authoritative_argv(tmp_path, capsys):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )

    assert main(
        ["experiment", "prepare-self-test", str(project.root), "--json"]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "readiness",
        "argv",
        "environment_fingerprint",
        "package_contract_sha256",
        "report_path",
        "registration_argv",
    }
    assert payload["readiness"] == "ready_for_explicit_self_test"
    assert Path(payload["argv"][0]).is_absolute()
    assert payload["argv"][1] == "experiment/code/main.py"
    assert payload["argv"][-1] == "--self-test"
    assert payload["registration_argv"] == [
        "researchclaw-codex",
        "experiment",
        "register-self-test",
        str(project.root.resolve()),
        "--report",
        "experiment/self_test_report.json",
        "--confirm-self-test",
        "--json",
    ]

    completed = subprocess.run(
        payload["argv"], cwd=project.root, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert main(payload["registration_argv"][1:]) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered["path"] == "experiment/self_test_report.json"


def test_prepare_self_test_cli_normalizes_package_and_environment_errors(
    tmp_path, monkeypatch, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )
    contract_path = project.root / "experiment/package_contract.json"
    contract_path.write_text("{}\n", encoding="utf-8")

    assert main(
        ["experiment", "prepare-self-test", str(project.root), "--json"]
    ) == 2
    assert capsys.readouterr().err == "error: experiment_package_invalid\n"

    project, _ = build_stage_twelve_project(
        tmp_path / "environment-project", register_self_test=False
    )
    monkeypatch.setattr(
        "researchclaw.core.experiment_package_contract.inspect_execution_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    assert main(
        ["experiment", "prepare-self-test", str(project.root), "--json"]
    ) == 2
    assert capsys.readouterr().err == "error: execution_environment_unavailable\n"


def test_resume_cli_reports_self_test_registration_command_before_approval(
    tmp_path, capsys
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )

    assert main(["status", str(project.root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["next_action"] == "prepare_experiment_self_test"
    assert "experiment prepare-self-test" in status["next_command"]

    assert main(["resume", str(project.root), "--json"]) == 0
    before = json.loads(capsys.readouterr().out)
    assert before["next_action"] == "prepare_experiment_self_test"
    assert before["approval_eligible"] is False
    assert shlex.split(before["next_command"]) == [
        "researchclaw-codex",
        "experiment",
        "prepare-self-test",
        str(project.root.resolve()),
        "--json",
    ]

    assert main(shlex.split(before["next_command"])[1:]) == 0
    prepared = json.loads(capsys.readouterr().out)
    completed = subprocess.run(
        prepared["argv"], cwd=project.root, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert main(prepared["registration_argv"][1:]) == 0
    capsys.readouterr()

    assert main(["resume", str(project.root), "--json"]) == 0
    after = json.loads(capsys.readouterr().out)
    assert after["next_action"] == "approve_experiment_execution"
    assert after["approval_eligible"] is True
    assert shlex.split(after["next_command"])[:2] == [
        "researchclaw-codex",
        "approve",
    ]


def test_experiment_register_self_test_cli_requires_confirmation(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_known_answer_self_test(project)

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--confirm-self-test" in captured.err


def test_experiment_register_self_test_cli_normalizes_invalid_report(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--confirm-self-test",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: experiment_self_test_required\n"


def test_json_status_normalizes_malformed_state_to_stderr(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["init", str(root), "--topic", "Formation energy", "--json"]) == 0
    capsys.readouterr()
    state_path = root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    del state["project_id"]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert main(["status", str(root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "project_id" in captured.err


def test_module_help_uses_the_public_codex_cli_name():
    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("usage: researchclaw-codex ")


def test_stage_prepare_cli_keeps_legacy_baseline_migration_opt_in(tmp_path, capsys):
    project = build_completed_validation_design_project(tmp_path / "project")
    _remove_stage_ten_snapshot(project)

    assert main(["stage", "prepare", str(project.root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "legacy Stage 10" in captured.err
    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "legacy_missing"


def test_stage_prepare_cli_explicitly_establishes_safe_legacy_baseline(
    tmp_path, capsys
):
    project = build_completed_validation_design_project(tmp_path / "project")
    _remove_stage_ten_snapshot(project)

    assert main(
        [
            "stage",
            "prepare",
            str(project.root),
            "--establish-legacy-baseline",
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage_id"] == 10
    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "captured"


def test_execution_recheck_cli_refreshes_declared_readiness(tmp_path, capsys):
    project, declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")

    assert main(["execution", "recheck", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "ready_for_execution"
    assert payload["approval_eligible"] is True
    assert payload["unmet_prerequisites"] == []
    assert len(payload["resource_plan_sha256"]) == 64
    assert captured.err == ""
    assert not (project.root / "experiment/results.json").exists()


def test_execution_recheck_cli_accepts_explicit_development_manifest(
    tmp_path, capsys
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    fixture = project.root / "experiment/dev_data/fixture.csv"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("cell_id\nC01\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(fixture.read_bytes()).hexdigest()
    manifest = project.root / "experiment/input_manifest.dev.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "synthetic_development_input",
                "evidence_eligible": False,
                "datasets": [{"dataset_id": "SYNTH_A"}],
                "cell_records": {"path": "experiment/dev_data/fixture.csv", "row_count": 1, "sha256": digest},
                "features": {"path": "experiment/dev_data/fixture.csv", "row_count": 1, "sha256": digest},
                "labels": {"path": "experiment/dev_data/fixture.csv"},
                "groups": {"independent_group_key": "condition_id"},
                "provenance": {"license_status": "not_required_synthetic", "research_evidence_use": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(
        [
            "execution",
            "recheck",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["readiness"] == "ready_for_development"
    assert payload["approval_eligible"] is False
    assert payload["input_manifest_path"] == "experiment/input_manifest.dev.json"


def test_execution_run_cli_completes_explicit_development_fixture(tmp_path, capsys):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)

    assert main(
        [
            "execution",
            "run",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--confirm-development-run",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "development_run_complete"
    assert payload["approval_eligible"] is False
    assert captured.err == ""
    assert (project.root / "experiment/dev_results.json").exists()


def test_execution_validate_result_cli_checks_existing_development_result(
    tmp_path, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    assert main(
        [
            "execution", "run", str(project.root),
            "--input-manifest", "experiment/input_manifest.dev.json",
            "--development", "--confirm-development-run", "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "execution", "validate-result", str(project.root),
            "--result", "experiment/dev_results.json",
            "--development", "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "development_result_valid"
    assert payload["approval_eligible"] is False
    assert payload["result_path"] == "experiment/dev_results.json"
    assert len(payload["result_sha256"]) == 64
    assert captured.err == ""


def test_execution_prepare_run_cli_emits_handoff_without_running_command(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )

    assert main(["execution", "prepare-run", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    contract = load_execution_contract(project.root)
    assert payload["readiness"] == "ready_for_explicit_execution"
    assert payload["result_path"] == "experiment/results.json"
    assert payload["bindings"] == contract["bindings"]
    assert payload["inputs"] == contract["inputs"]
    assert payload["result_template"] == contract["result_template"]
    assert captured.err == ""
    assert not (project.root / "project-code-executed").exists()


def test_execution_prepare_run_cli_displays_a_quoted_argv_command(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    assert main(["execution", "prepare-run", str(project.root)]) == 0

    captured = capsys.readouterr()
    status = prepare_research_execution(ResearchProject.open(project.root))
    assert captured.out.strip() == shlex.join(status.argv)
    assert captured.err == ""


def test_execution_prepare_run_cli_rejects_unapproved_project_without_mutating_state(
    tmp_path, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="ready_for_execution"
    )
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(["execution", "prepare-run", str(project.root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "execution_approval_invalid" in captured.err
    assert state_path.read_bytes() == state_before
    assert not (project.root / "experiment/execution_contract.json").exists()


def test_execution_register_result_cli_advances_to_thirteen(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "research_result_registered"
    assert payload["current_stage"] == 13
    assert captured.err == ""


def test_status_cli_does_not_reuse_stage_twelve_readiness_at_stage_thirteen(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(
        project, load_execution_contract(project.root)
    )
    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(["status", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["current_stage"] == 13
    assert payload["execution_readiness"] is None
    assert payload["unmet_prerequisites"] == []
    assert payload["approval_eligible"] is False
    assert captured.err == ""


@pytest.mark.parametrize("omitted_flag", ["--result", "--confirm-research-result"])
def test_execution_register_result_cli_requires_explicit_research_intent(
    tmp_path, capsys, omitted_flag
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()
    arguments = [
        "execution",
        "register-result",
        str(project.root),
        "--result",
        "experiment/results.json",
        "--confirm-research-result",
        "--json",
    ]
    index = arguments.index(omitted_flag)
    del arguments[index : index + (2 if omitted_flag == "--result" else 1)]

    assert main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert omitted_flag in captured.err
    assert state_path.read_bytes() == state_before


def test_execution_register_result_cli_rejects_invalid_pending_recovery_without_mutating_state(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    pending_path = (
        project.root / ".researchclaw/research-result-registration.pending.json"
    )
    pending_path.write_bytes(b'{"schema_version":3,"schema_version":3}')
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: research_result_registration_recovery_invalid\n"
    assert state_path.read_bytes() == state_before


def test_execution_register_result_cli_normalizes_malformed_event_log_without_mutating_state(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(
        project, load_execution_contract(project.root)
    )
    event_path = project.root / "evaluation/events.jsonl"
    event_path.write_bytes(event_path.read_bytes() + b"{not-json}\n")
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: research_result_registration_recovery_invalid\n"
    assert state_path.read_bytes() == state_before
    assert event_path.read_bytes().endswith(b"{not-json}\n")


def test_development_run_wrong_stage_does_not_normalize_legacy_state(tmp_path, capsys):
    project = ResearchProject.create(tmp_path / "project", "Formation energy", "materials_ai")
    _remove_stage_ten_snapshot(project)
    state_path = project.root / ".researchclaw/state.json"
    before = state_path.read_bytes()

    assert main([
        "execution", "run", str(project.root),
        "--input-manifest", "experiment/input_manifest.dev.json",
        "--development", "--confirm-development-run", "--json",
    ]) == 2

    assert state_path.read_bytes() == before
    assert "Stage 12" in capsys.readouterr().err


def test_development_run_ignores_project_local_numpy_shadow(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    marker = project.root / "numpy-shadow-executed"
    (project.root / "numpy.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "raise ImportError('project shadow must not execute')\n",
        encoding="utf-8",
    )
    repository_root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "PYTHONPATH": str(repository_root)}

    result = subprocess.run(
        [
            sys.executable, "-m", "researchclaw.codex.cli", "execution", "run",
            str(project.root), "--input-manifest", "experiment/input_manifest.dev.json",
            "--development", "--confirm-development-run", "--json",
        ],
        cwd=project.root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert json.loads(result.stdout)["readiness"] == "development_run_complete"


def test_numpy_absence_is_bounded_to_development_execution_in_fresh_process(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    prior_result = project.root / "experiment/dev_results.json"
    prior_result.write_bytes(b'{"prior":true}\n')
    blocker = tmp_path / "blocked-import"
    blocker.mkdir()
    (blocker / "numpy.py").write_text(
        "raise ImportError('NumPy deliberately unavailable')\n", encoding="utf-8"
    )
    repository_root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(blocker), str(repository_root))),
    }

    ordinary = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "--help"],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    development = subprocess.run(
        [
            sys.executable,
            "-m",
            "researchclaw.codex.cli",
            "execution",
            "run",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--confirm-development-run",
            "--json",
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ordinary.returncode == 0
    assert ordinary.stdout.startswith("usage: researchclaw-codex ")
    assert development.returncode == 2
    assert development.stdout == ""
    assert development.stderr == "error: numpy_unavailable\n"
    assert prior_result.read_bytes() == b'{"prior":true}\n'
    event = json.loads(
        (project.root / "evaluation/events.jsonl").read_text().splitlines()[-1]
    )
    assert event["type"] == "development_execution_failed"
    assert event["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "numpy_unavailable",
    }


@pytest.mark.parametrize(
    ("omitted_flag", "expected_flag"),
    [
        ("--input-manifest", "--input-manifest"),
        ("--development", "--development"),
        ("--confirm-development-run", "--confirm-development-run"),
    ],
)
def test_execution_run_cli_requires_explicit_development_intent(
    tmp_path, capsys, omitted_flag, expected_flag
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    arguments = [
        "execution",
        "run",
        str(project.root),
        "--input-manifest",
        "experiment/input_manifest.dev.json",
        "--development",
        "--confirm-development-run",
        "--json",
    ]
    index = arguments.index(omitted_flag)
    del arguments[index : index + (2 if omitted_flag == "--input-manifest" else 1)]

    assert main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected_flag in captured.err
    assert not (project.root / "experiment/dev_results.json").exists()


@pytest.mark.parametrize("command", ["approve", "recheck"])
@pytest.mark.parametrize(
    ("lineage_damage", "expected_stage"),
    [
        ("tampered-package-file", 10),
        ("missing-stage-nine-approval", 9),
        ("rejected-stage-nine-approval", 9),
    ],
)
def test_stage_twelve_cli_commands_normalize_durable_lineage_before_mutating(
    tmp_path,
    capsys,
    command,
    lineage_damage,
    expected_stage,
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / f"{command}-{lineage_damage}"
    )
    if lineage_damage == "tampered-package-file":
        main_path = project.root / "experiment/code/main.py"
        main_path.write_bytes(main_path.read_bytes() + b"\n# tampered after validation\n")
    else:
        approval_path = project.root / "approvals/stage-09.json"
        if lineage_damage == "missing-stage-nine-approval":
            approval_path.unlink()
        else:
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            approval["decision"] = "reject"
            approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")

    argv = (
        ["approve", str(project.root), "--decision", "approve", "--json"]
        if command == "approve"
        else ["execution", "recheck", str(project.root), "--json"]
    )
    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    state = ResearchProject.open(project.root).state
    assert state.current_stage == expected_stage
    assert state.status.value == "needs_revision"
    assert state.next_action == (
        "validate_experiment_package"
        if lineage_damage == "tampered-package-file"
        else "validate_stage"
    )
    assert not (project.root / "approvals/stage-12.json").exists()
