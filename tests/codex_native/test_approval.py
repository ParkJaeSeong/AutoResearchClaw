import hashlib
import json
from dataclasses import replace
import subprocess
import sys

import pytest

from researchclaw.core import events as events_module
from researchclaw.core import experiment_package_contract as experiment_contract
from researchclaw.codex.cli import main
from researchclaw.core.approval import approve_current_gate, verify_current_approval
from researchclaw.core.events import EvaluationEvent, EventLog, event_log_for
from researchclaw.core.experiment_package_contract import (
    SELF_TEST_REPORT_PATH,
    _current_registered_self_test,
    register_experiment_self_test,
    validate_experiment_package_contract,
)
from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.state import StateStore
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import (
    build_self_test_registration_project,
    build_stage_twelve_project,
    complete_first_four_stages,
)


def _project_at_stage_five_gate(root):
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    shortlist = project.root / "literature" / "shortlist.jsonl"
    shortlist.write_text(
        json.dumps(
            {
                "source_id": "source-1",
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


def test_stage_five_approval_advances_to_stage_six(tmp_path):
    project, _ = _project_at_stage_five_gate(tmp_path / "demo")

    record = approve_current_gate(project, "approve", "Use this corpus")

    reopened = ResearchProject.open(project.root)
    assert record.artifact_hashes["literature/shortlist.jsonl"]
    assert reopened.state.completed_stages[-1] == 5
    assert reopened.state.current_stage == 6
    assert reopened.state.status.value == "ready"
    assert reopened.state.next_action == "prepare_stage"
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


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_stage_twelve_approval_refuses_needs_input(tmp_path, decision):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / decision,
        readiness="needs_input",
    )

    with pytest.raises(ValueError, match="execution prerequisites are not ready"):
        approve_current_gate(project, decision, "Run it")


def test_stage_twelve_approval_requires_registered_self_test(tmp_path):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )

    assert project.status_dict()["approval_eligible"] is False

    with pytest.raises(ValueError, match="experiment_self_test_required"):
        approve_current_gate(project, "approve", "Run it")


def test_register_experiment_self_test_records_artifact_and_event_at_gate(tmp_path):
    project = build_self_test_registration_project(tmp_path / "project")
    package = validate_experiment_package_contract(project)
    completed = subprocess.run(
        [sys.executable, "experiment/code/main.py", *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    state_before = project.state

    artifact = register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 12
    assert reopened.state.status.value == "awaiting_approval"
    assert reopened.state.next_action == "approve_experiment_execution"
    assert reopened.state.completed_stages == state_before.completed_stages
    assert reopened.state.artifacts[SELF_TEST_REPORT_PATH] == artifact
    event = json.loads(
        (project.root / "evaluation/events.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert event["type"] == "experiment_self_test_registered"
    assert event["payload"] == {
        "path": artifact.path,
        "sha256": artifact.sha256,
        "size": artifact.size,
    }


def _run_external_self_test(project):
    package = validate_experiment_package_contract(project)
    completed = subprocess.run(
        [sys.executable, "experiment/code/main.py", *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def _current_report_ref(project):
    report = project.root / SELF_TEST_REPORT_PATH
    payload = report.read_bytes()
    return ArtifactRef(
        path=SELF_TEST_REPORT_PATH,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )


def test_self_test_registration_event_append_failure_leaves_gate_ineligible(
    tmp_path, monkeypatch
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    original_append = EventLog.append_locked

    def fail_append(_self, _event, *, expected_offset):
        raise OSError("injected event failure")

    monkeypatch.setattr(EventLog, "append_locked", fail_append)
    with pytest.raises(OSError, match="injected event failure"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    reopened = ResearchProject.open(project.root)
    assert SELF_TEST_REPORT_PATH not in reopened.state.artifacts
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(reopened)

    monkeypatch.setattr(EventLog, "append_locked", original_append)
    artifact = register_experiment_self_test(reopened, SELF_TEST_REPORT_PATH)
    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1


def test_self_test_registration_state_save_failure_is_recoverable_and_idempotent(
    tmp_path, monkeypatch
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    original_save = StateStore.save
    failed = False

    def fail_registration_save(store, state):
        nonlocal failed
        if SELF_TEST_REPORT_PATH in state.artifacts and not failed:
            failed = True
            raise OSError("injected state failure")
        return original_save(store, state)

    monkeypatch.setattr(StateStore, "save", fail_registration_save)
    with pytest.raises(OSError, match="injected state failure"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    reopened = ResearchProject.open(project.root)
    assert SELF_TEST_REPORT_PATH not in reopened.state.artifacts
    assert _self_test_pending_path(project).is_file()
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(reopened)

    artifact = register_experiment_self_test(reopened, SELF_TEST_REPORT_PATH)
    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact
    assert not _self_test_pending_path(project).exists()
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1

    assert register_experiment_self_test(
        ResearchProject.open(project.root), SELF_TEST_REPORT_PATH
    ) == artifact
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1


def test_exact_self_test_artifact_ref_without_registration_event_is_ineligible(tmp_path):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )
    _run_external_self_test(project)
    artifact = _current_report_ref(project)
    project.persist_state(
        replace(
            project.state,
            artifacts={**project.state.artifacts, SELF_TEST_REPORT_PATH: artifact},
        )
    )

    reopened = ResearchProject.open(project.root)
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(reopened)
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        approve_current_gate(reopened, "approve", "Run it")


def test_partial_self_test_registration_event_does_not_ground_forged_state(tmp_path):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    artifact = _current_report_ref(project)
    event_log_for(project.root).append(
        EvaluationEvent.create(
            "experiment_self_test_registered",
            project.state.project_id,
            {"path": artifact.path, "sha256": artifact.sha256},
        )
    )
    project.persist_state(
        replace(
            project.state,
            artifacts={**project.state.artifacts, SELF_TEST_REPORT_PATH: artifact},
        )
    )

    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(ResearchProject.open(project.root))

    assert register_experiment_self_test(
        ResearchProject.open(project.root), SELF_TEST_REPORT_PATH
    ) == artifact
    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact


def _self_test_pending_path(project):
    return (
        project.root
        / ".researchclaw/experiment-self-test-registration.pending.json"
    )


def test_self_test_registration_repairs_only_its_owned_torn_event_tail(
    tmp_path, monkeypatch
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    event_path = project.root / "evaluation/events.jsonl"
    prefix = event_path.read_bytes()
    prior_events = event_log_for(project.root).read_all()
    original_write = events_module.os.write
    writes = 0

    def tear_registration_write(descriptor, payload):
        nonlocal writes
        writes += 1
        if writes == 1:
            fragment_size = max(1, len(payload) * 3 // 4)
            return original_write(descriptor, payload[:fragment_size])
        raise OSError("injected torn self-test event write")

    monkeypatch.setattr(events_module.os, "write", tear_registration_write)
    with pytest.raises(OSError, match="injected torn self-test event write"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    torn = event_path.read_bytes()
    assert torn.startswith(prefix)
    assert len(torn) > len(prefix)
    assert _self_test_pending_path(project).is_file()
    reopened = ResearchProject.open(project.root)
    assert SELF_TEST_REPORT_PATH not in reopened.state.artifacts
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(reopened)

    monkeypatch.setattr(events_module.os, "write", original_write)
    artifact = register_experiment_self_test(reopened, SELF_TEST_REPORT_PATH)

    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact
    assert not _self_test_pending_path(project).exists()
    events = event_log_for(project.root).read_all()
    assert events[: len(prior_events)] == prior_events
    assert sum(
        event.type == "experiment_self_test_registered" for event in events
    ) == 1
    assert event_path.read_bytes().startswith(prefix)


def test_self_test_registration_recovers_after_pending_record_write(
    tmp_path, monkeypatch
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    original_persist = experiment_contract._persist_self_test_registration_pending
    failed = False

    def persist_then_fail(persist_project, pending):
        nonlocal failed
        original_persist(persist_project, pending)
        if not failed:
            failed = True
            raise OSError("injected failure after pending write")

    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        persist_then_fail,
    )
    with pytest.raises(OSError, match="injected failure after pending write"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    assert _self_test_pending_path(project).is_file()
    assert SELF_TEST_REPORT_PATH not in ResearchProject.open(project.root).state.artifacts
    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        original_persist,
    )

    artifact = register_experiment_self_test(project, SELF_TEST_REPORT_PATH)
    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact
    assert not _self_test_pending_path(project).exists()


def test_self_test_pending_recovers_after_public_status_and_handoff_normalize_prior(
    tmp_path, monkeypatch
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )
    _run_external_self_test(project)
    original_persist = experiment_contract._persist_self_test_registration_pending
    failed = False

    def persist_then_fail(persist_project, pending):
        nonlocal failed
        original_persist(persist_project, pending)
        if not failed:
            failed = True
            raise OSError("injected failure after pending write")

    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        persist_then_fail,
    )
    with pytest.raises(OSError, match="injected failure after pending write"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)
    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        original_persist,
    )
    event_path = project.root / "evaluation/events.jsonl"
    event_prefix = event_path.read_bytes()

    status = ResearchProject.open(project.root).status_dict()
    handoff = ResearchProject.open(project.root).build_handoff()

    assert status["next_action"] == "register_experiment_self_test"
    assert handoff.next_action == "register_experiment_self_test"
    assert event_path.read_bytes() == event_prefix
    normalized = ResearchProject.open(project.root)
    assert normalized.state.next_action == "register_experiment_self_test"
    assert SELF_TEST_REPORT_PATH not in normalized.state.artifacts

    artifact = register_experiment_self_test(normalized, SELF_TEST_REPORT_PATH)

    reopened = ResearchProject.open(project.root)
    assert _current_registered_self_test(reopened) == artifact
    assert reopened.state.artifacts[SELF_TEST_REPORT_PATH] == artifact
    assert not _self_test_pending_path(project).exists()
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1


@pytest.mark.parametrize("drift", ["unrelated_artifact", "retry_count"])
def test_self_test_pending_rejects_normalized_prior_with_other_state_drift(
    tmp_path, monkeypatch, drift
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / drift, register_self_test=False
    )
    _run_external_self_test(project)
    original_persist = experiment_contract._persist_self_test_registration_pending

    def persist_then_fail(persist_project, pending):
        original_persist(persist_project, pending)
        raise OSError("injected failure after pending write")

    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        persist_then_fail,
    )
    with pytest.raises(OSError, match="injected failure after pending write"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)
    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        original_persist,
    )
    normalized = ResearchProject.open(project.root)
    normalized.status_dict()
    normalized = ResearchProject.open(project.root)
    if drift == "unrelated_artifact":
        drifted_state = replace(
            normalized.state,
            artifacts={
                **normalized.state.artifacts,
                "attacker/unrelated.bin": ArtifactRef(
                    path="attacker/unrelated.bin",
                    sha256="0" * 64,
                    size=0,
                ),
            },
        )
    else:
        drifted_state = replace(
            normalized.state,
            retry_counts={**normalized.state.retry_counts, "12": 99},
        )
    normalized.persist_state(drifted_state)
    event_before = (project.root / "evaluation/events.jsonl").read_bytes()

    with pytest.raises(
        ValueError, match="experiment_self_test_registration_recovery_invalid"
    ):
        register_experiment_self_test(
            ResearchProject.open(project.root), SELF_TEST_REPORT_PATH
        )

    assert (project.root / "evaluation/events.jsonl").read_bytes() == event_before
    assert _self_test_pending_path(project).is_file()
    assert SELF_TEST_REPORT_PATH not in ResearchProject.open(project.root).state.artifacts


def test_self_test_registration_recovers_state_before_pending_clear(
    tmp_path, monkeypatch
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )
    _run_external_self_test(project)
    original_clear = experiment_contract._clear_self_test_registration_pending

    def fail_clear(_project):
        raise OSError("injected failure before pending clear")

    monkeypatch.setattr(
        experiment_contract, "_clear_self_test_registration_pending", fail_clear
    )
    with pytest.raises(OSError, match="injected failure before pending clear"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    reopened = ResearchProject.open(project.root)
    assert SELF_TEST_REPORT_PATH in reopened.state.artifacts
    assert _self_test_pending_path(project).is_file()
    with pytest.raises(ValueError, match="experiment_self_test_required"):
        _current_registered_self_test(reopened)
    assert reopened.status_dict()["next_action"] == "register_experiment_self_test"
    monkeypatch.setattr(
        experiment_contract,
        "_clear_self_test_registration_pending",
        original_clear,
    )

    artifact = register_experiment_self_test(reopened, SELF_TEST_REPORT_PATH)
    assert _current_registered_self_test(ResearchProject.open(project.root)) == artifact
    assert not _self_test_pending_path(project).exists()
    assert sum(
        event.type == "experiment_self_test_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1


@pytest.mark.parametrize("tail_kind", ["changed_prefix", "unrelated_complete"])
def test_self_test_registration_never_repairs_unowned_event_log_bytes(
    tmp_path, monkeypatch, tail_kind
):
    project = build_self_test_registration_project(tmp_path / tail_kind)
    _run_external_self_test(project)
    original_persist = experiment_contract._persist_self_test_registration_pending

    def persist_then_fail(persist_project, pending):
        original_persist(persist_project, pending)
        raise OSError("stop after pending ownership record")

    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        persist_then_fail,
    )
    with pytest.raises(OSError, match="stop after pending ownership record"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)
    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        original_persist,
    )
    event_path = project.root / "evaluation/events.jsonl"
    if tail_kind == "changed_prefix":
        damaged = bytearray(event_path.read_bytes())
        damaged[0] = ord("[") if damaged[0] != ord("[") else ord("{")
        event_path.write_bytes(damaged)
    else:
        event_log_for(project.root).append(
            EvaluationEvent.create(
                "unrelated_complete_event",
                project.state.project_id,
                {"source": "external"},
            )
        )
    before_retry = event_path.read_bytes()

    with pytest.raises(
        ValueError, match="experiment_self_test_registration_recovery_invalid"
    ):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    assert event_path.read_bytes() == before_retry
    assert SELF_TEST_REPORT_PATH not in ResearchProject.open(project.root).state.artifacts


def test_self_test_registration_does_not_repair_attacker_tail_without_ownership_marker(
    tmp_path, monkeypatch
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    original_persist = experiment_contract._persist_self_test_registration_pending

    def persist_then_fail(persist_project, pending):
        original_persist(persist_project, pending)
        raise OSError("stop after pending ownership record")

    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        persist_then_fail,
    )
    with pytest.raises(OSError, match="stop after pending ownership record"):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)
    monkeypatch.setattr(
        experiment_contract,
        "_persist_self_test_registration_pending",
        original_persist,
    )
    pending = json.loads(_self_test_pending_path(project).read_text(encoding="utf-8"))
    record = json.dumps(
        pending["event"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8") + b"\n"
    event_path = project.root / "evaluation/events.jsonl"
    before = event_path.read_bytes() + record[:32]
    event_path.write_bytes(before)

    with pytest.raises(
        ValueError, match="experiment_self_test_registration_recovery_invalid"
    ):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    assert event_path.read_bytes() == before


def test_self_test_registration_normalizes_unowned_malformed_tail_without_repair(
    tmp_path
):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_external_self_test(project)
    event_path = project.root / "evaluation/events.jsonl"
    attacker_tail = event_path.read_bytes() + b'{"attacker":'
    event_path.write_bytes(attacker_tail)

    with pytest.raises(
        ValueError, match="experiment_self_test_registration_recovery_invalid"
    ):
        register_experiment_self_test(project, SELF_TEST_REPORT_PATH)

    assert event_path.read_bytes() == attacker_tail
    assert not _self_test_pending_path(project).exists()
    assert SELF_TEST_REPORT_PATH not in ResearchProject.open(project.root).state.artifacts


def test_execution_approval_binds_gate_and_self_test_artifacts_without_executing(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    completed_before = project.state.completed_stages

    record = approve_current_gate(project, "approve", "Run it")

    assert set(record.artifact_hashes) == {
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
        "experiment/self_test_report.json",
    }
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 12
    assert reopened.state.completed_stages == completed_before
    assert reopened.state.status.value == "ready"
    assert reopened.state.next_action == "report_resource_plan_milestone_only"
    assert reopened.status_dict()["approval_eligible"] is False
    assert not (project.root / "experiment/results.json").exists()
    assert json.loads(
        (project.root / "approvals/stage-12.json").read_text(encoding="utf-8")
    )["note"] == "Run it"
    handoff = reopened.build_handoff()
    assert handoff.next_action == "report_resource_plan_milestone_only"
    assert " approve " not in f" {handoff.next_command} "
    assert "stage prepare" not in handoff.next_command


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiment/package_contract.json",
        "experiment/self_test_fixture.json",
    ],
)
def test_stage_twelve_approval_rejects_registered_self_test_identity_drift(
    tmp_path, relative_path
):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    path = project.root / relative_path
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="experiment_self_test_required"):
        approve_current_gate(ResearchProject.open(project.root), "approve", "Run it")


def test_stage_twelve_approval_rechecks_readiness_against_current_inputs(tmp_path):
    project, declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")
    execution_gate = __import__(
        "researchclaw.core.execution_gate",
        fromlist=["recheck_execution_readiness"],
    )
    execution_gate.recheck_execution_readiness(project)
    declared_input.unlink()

    with pytest.raises(ValueError, match="execution prerequisites are not ready"):
        approve_current_gate(ResearchProject.open(project.root), "approve", "Run it")


@pytest.mark.parametrize(
    ("lineage_damage", "expected_stage"),
    [
        ("tampered-package-file", 10),
        ("missing-stage-nine-approval", 9),
        ("rejected-stage-nine-approval", 9),
    ],
)
def test_stage_twelve_approval_normalizes_all_durable_lineage_before_deciding(
    tmp_path,
    lineage_damage,
    expected_stage,
):
    project, _declared_input = build_stage_twelve_project(tmp_path / lineage_damage)
    if lineage_damage == "tampered-package-file":
        main = project.root / "experiment/code/main.py"
        main.write_bytes(main.read_bytes() + b"\n# tampered after validation\n")
    else:
        approval_path = project.root / "approvals/stage-09.json"
        if lineage_damage == "missing-stage-nine-approval":
            approval_path.unlink()
        else:
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            approval["decision"] = "reject"
            approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        approve_current_gate(project, "approve", "Run it")

    state = ResearchProject.open(project.root).state
    assert state.current_stage == expected_stage
    assert state.status.value == "needs_revision"
    assert state.next_action == (
        "validate_experiment_package"
        if lineage_damage == "tampered-package-file"
        else "validate_stage"
    )
    assert not (project.root / "approvals/stage-12.json").exists()


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
    ],
)
def test_modifying_any_execution_gate_artifact_invalidates_approval(
    tmp_path,
    relative_path,
):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    record = approve_current_gate(project, "approve", "Run it")

    path = project.root / relative_path
    path.write_bytes(path.read_bytes() + b"\n")

    assert verify_current_approval(project.root, record) is False


def test_status_rewinds_when_a_bound_execution_artifact_changes(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    approve_current_gate(project, "approve", "Run it")
    design = project.root / "experiment/design.json"
    design.write_bytes(design.read_bytes() + b"\n")

    status = ResearchProject.open(project.root).status_dict()

    assert status["current_stage"] == 9
    assert status["status"] == "needs_revision"
    assert status["next_action"] == "validate_stage"
    assert status["approval_eligible"] is False


def test_status_reopens_stage_twelve_gate_when_approval_record_is_missing(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    approve_current_gate(project, "approve", "Run it")
    (project.root / "approvals/stage-12.json").unlink()

    status = ResearchProject.open(project.root).status_dict()
    handoff = ResearchProject.open(project.root).build_handoff().to_dict()

    for payload in (status, handoff):
        assert payload["current_stage"] == 12
        assert payload["status"] == "awaiting_approval"
        assert payload["next_action"] == "approve_experiment_execution"
        assert payload["approval_eligible"] is True


def test_reject_keeps_stage_twelve_safely_locked(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")

    record = approve_current_gate(project, "reject", "Do not run")

    reopened = ResearchProject.open(project.root)
    assert record.note == "Do not run"
    assert reopened.state.current_stage == 12
    assert reopened.state.completed_stages[-1] == 11
    assert reopened.state.status.value == "awaiting_approval"
    assert reopened.state.next_action == "report_missing_execution_inputs"
    assert reopened.status_dict()["approval_eligible"] is False
    assert not (project.root / "experiment/results.json").exists()
    status = reopened.status_dict()
    handoff = reopened.build_handoff().to_dict()
    for payload in (status, handoff):
        assert payload["status"] == "awaiting_approval"
        assert payload["next_action"] == "report_missing_execution_inputs"
        assert payload["execution_readiness"] == "ready_for_execution"
        assert payload["approval_eligible"] is False
    assert " approve " not in f" {handoff['next_command']} "


def test_explicit_approve_supersedes_a_current_stage_twelve_rejection(tmp_path):
    project, _declared_input = build_stage_twelve_project(tmp_path / "project")
    rejected = approve_current_gate(project, "reject", "Do not run")

    approved = approve_current_gate(
        ResearchProject.open(project.root),
        "approve",
        "Run after reconsideration",
    )

    assert rejected.decision == "reject"
    assert approved.decision == "approve"
    assert approved.note == "Run after reconsideration"
    assert verify_current_approval(project.root, approved) is True
    reopened = ResearchProject.open(project.root)
    assert reopened.state.status.value == "ready"
    assert reopened.state.next_action == "report_resource_plan_milestone_only"
    assert not (project.root / "experiment/results.json").exists()
