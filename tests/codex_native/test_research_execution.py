import hashlib
import json
import os
import runpy
import threading
from copy import deepcopy
from dataclasses import replace

import pytest

import researchclaw.core.research_execution as research_execution
from researchclaw.core.events import EventLog, event_log_for
from researchclaw.core.models import ArtifactRef, StageStatus
from researchclaw.core.project import ResearchProject
from researchclaw.core.execution_gate import _read_project_file_snapshot
from researchclaw.core.research_execution import (
    EXECUTION_CONTRACT_PATH,
    _build_execution_contract,
    prepare_research_execution,
    register_research_result,
    validate_research_result,
)
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    load_execution_contract,
    write_contract_bound_research_result,
)


def test_register_result_completes_stage_twelve(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)

    before = ResearchProject.open(project.root).state
    approval_before = (project.root / "approvals/stage-12.json").read_bytes()

    status = register_research_result(project, "experiment/results.json")

    reopened = ResearchProject.open(project.root)
    assert status.readiness == "research_result_registered"
    assert status.approval_eligible is False
    assert status.result_path == "experiment/results.json"
    assert status.result_sha256 == hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert status.current_stage == 13
    assert status.next_action == "prepare_stage"
    assert status.to_dict() == {
        "readiness": "research_result_registered",
        "approval_eligible": False,
        "result_path": "experiment/results.json",
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "current_stage": 13,
        "next_action": "prepare_stage",
    }
    assert reopened.state.current_stage == 13
    assert reopened.state.status == StageStatus.READY
    assert reopened.state.completed_stages.count(12) == 1
    assert reopened.state.completed_stages == (*before.completed_stages, 12)
    assert reopened.state.next_action == "prepare_stage"
    assert reopened.state.execution_policy == before.execution_policy
    assert reopened.state.retry_counts == before.retry_counts
    assert reopened.state.stage_10_snapshot == before.stage_10_snapshot
    assert reopened.state.last_error is None
    assert {
        path: artifact
        for path, artifact in reopened.state.artifacts.items()
        if path != "experiment/results.json"
    } == before.artifacts
    assert reopened.state.artifacts["experiment/results.json"].sha256 == hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    assert reopened.state.artifacts["experiment/results.json"].size == len(
        result_path.read_bytes()
    )
    assert (project.root / "approvals/stage-12.json").read_bytes() == approval_before
    matching_events = [
        event
        for event in event_log_for(project.root).read_all()
        if event.type == "research_result_registered"
    ]
    assert len(matching_events) == 1
    assert matching_events[0].payload == {
        "contract_path": "experiment/execution_contract.json",
        "contract_sha256": hashlib.sha256(
            (project.root / "experiment/execution_contract.json").read_bytes()
        ).hexdigest(),
        "result_path": "experiment/results.json",
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "metric_count": 1,
        "input_count": 1,
    }


def test_register_result_rechecks_bytes_immediately_before_persistence(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    original_validate = research_execution.validate_research_result

    def validate_then_replace(project, relative_path):
        validated = original_validate(project, relative_path)
        result_path.write_bytes(b'{"changed":true}\n')
        return validated

    monkeypatch.setattr(
        research_execution, "validate_research_result", validate_then_replace
    )

    with pytest.raises(ValueError, match="^research_result_file_invalid$"):
        register_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert ResearchProject.open(project.root).state.current_stage == 12
    event = event_log_for(project.root).read_all()[-1]
    assert event.type == "research_result_registration_failed"
    assert event.payload["error_category"] == "research_result_file_invalid"
    assert set(event.payload) <= {
        "error_category",
        "contract_path",
        "contract_sha256",
        "result_path",
        "result_sha256",
    }


def test_register_result_restores_prior_state_when_result_changes_during_persistence(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    original_persist = ResearchProject.persist_state

    def persist_after_replacing_result(self, state):
        if state.current_stage == 13:
            result_path.write_bytes(b'{"changed-during-persistence":true}\n')
        return original_persist(self, state)

    monkeypatch.setattr(
        ResearchProject, "persist_state", persist_after_replacing_result
    )

    with pytest.raises(ValueError, match="^research_result_file_invalid$"):
        register_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 12
    assert "experiment/results.json" not in reopened.state.artifacts
    assert not (
        project.root
        / ".researchclaw/research-result-registration.pending.json"
    ).exists()
    events = event_log_for(project.root).read_all()
    assert sum(event.type == "research_result_registered" for event in events) == 0
    assert events[-1].type == "research_result_registration_failed"
    assert set(events[-1].payload) <= {
        "error_category",
        "contract_path",
        "contract_sha256",
        "result_path",
        "result_sha256",
    }


@pytest.mark.parametrize("append_then_fail", (False, True), ids=("before", "after"))
def test_register_result_recovers_event_append_failure_exactly_once(
    tmp_path, monkeypatch, append_then_fail
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    original_append = EventLog.append
    failed = False

    def fail_first_success_append(self, event):
        nonlocal failed
        if event.type == "research_result_registered" and not failed:
            failed = True
            if append_then_fail:
                original_append(self, event)
            raise OSError("injected success-event append failure")
        return original_append(self, event)

    monkeypatch.setattr(EventLog, "append", fail_first_success_append)

    with pytest.raises(OSError, match="injected success-event append failure"):
        register_research_result(project, "experiment/results.json")

    pending_path = (
        project.root
        / ".researchclaw/research-result-registration.pending.json"
    )
    assert pending_path.is_file()
    assert ResearchProject.open(project.root).state.current_stage == 13
    monkeypatch.setattr(EventLog, "append", original_append)

    recovered = register_research_result(project, "experiment/results.json")

    assert recovered.current_stage == 13
    assert not pending_path.exists()
    reopened = ResearchProject.open(project.root)
    assert reopened.state.completed_stages.count(12) == 1
    matching = [
        event
        for event in event_log_for(project.root).read_all()
        if event.type == "research_result_registered"
    ]
    assert len(matching) == 1


def test_concurrent_registrations_are_serialized_to_one_logical_success(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    original_validate = research_execution.validate_research_result
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    call_count = 0
    count_lock = threading.Lock()

    def controlled_validate(project, result_path):
        nonlocal call_count
        with count_lock:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(2.0)
        else:
            second_entered.set()
        return original_validate(project, result_path)

    monkeypatch.setattr(
        research_execution, "validate_research_result", controlled_validate
    )
    statuses = []
    errors = []

    def register():
        try:
            statuses.append(
                register_research_result(project, "experiment/results.json")
            )
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=register)
    second = threading.Thread(target=register)
    first.start()
    assert first_entered.wait(1.0)
    second.start()
    try:
        assert not second_entered.wait(0.2)
    finally:
        release_first.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(statuses) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "execution_approval_invalid"
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 13
    assert reopened.state.completed_stages.count(12) == 1
    matching = [
        event
        for event in event_log_for(project.root).read_all()
        if event.type == "research_result_registered"
    ]
    assert len(matching) == 1
    assert not (
        project.root
        / ".researchclaw/research-result-registration.pending.json"
    ).exists()


def test_register_result_rejects_duplicate_registration_without_state_change(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    register_research_result(project, "experiment/results.json")
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="^execution_approval_invalid$"):
        register_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 13
    assert reopened.state.completed_stages.count(12) == 1
    events = event_log_for(project.root).read_all()
    assert sum(event.type == "research_result_registered" for event in events) == 1
    assert events[-1].type == "research_result_registration_failed"
    assert events[-1].payload["error_category"] == "execution_approval_invalid"


def test_register_result_retry_succeeds_after_invalid_result_is_corrected(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract, status="partial")

    with pytest.raises(ValueError, match="^research_result_schema_invalid$"):
        register_research_result(project, "experiment/results.json")

    write_contract_bound_research_result(project, contract)
    status = register_research_result(project, "experiment/results.json")

    reopened = ResearchProject.open(project.root)
    assert status.current_stage == 13
    assert reopened.state.completed_stages.count(12) == 1
    events = event_log_for(project.root).read_all()
    assert [
        event.type
        for event in events
        if event.type.startswith("research_result_registration")
        or event.type == "research_result_registered"
    ] == ["research_result_registration_failed", "research_result_registered"]


def test_register_result_normalizes_unexpected_failure_text_in_event(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)

    def fail_with_untrusted_detail(_project, _result_path):
        raise ValueError("secret detail that must not enter the event")

    monkeypatch.setattr(
        research_execution, "validate_research_result", fail_with_untrusted_detail
    )

    with pytest.raises(ValueError, match="secret detail"):
        register_research_result(project, "experiment/results.json")

    event = event_log_for(project.root).read_all()[-1]
    assert event.type == "research_result_registration_failed"
    assert event.payload["error_category"] == "research_result_registration_failed"
    assert "secret" not in json.dumps(event.payload)


def test_validate_research_result_accepts_exact_binding_without_mutation(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    controls = {
        relative: (project.root / relative).read_bytes()
        for relative in (
            ".researchclaw/state.json",
            "evaluation/events.jsonl",
            "approvals/stage-12.json",
            "experiment/resources.json",
            "experiment/execution_contract.json",
            "experiment/results.json",
        )
    }

    validated = validate_research_result(project, "experiment/results.json")

    assert validated.result_sha256 == hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert validated.metric_count == 1
    assert validated.input_count == 1
    with pytest.raises(TypeError):
        validated.payload["status"] = "failed"
    with pytest.raises(TypeError):
        validated.payload["metrics"]["primary"]["value"] = 0
    assert {
        relative: (project.root / relative).read_bytes() for relative in controls
    } == controls


@pytest.mark.parametrize("operation", ("prepare", "validate"))
@pytest.mark.parametrize("approval_case", ("symlink", "duplicate-key"))
def test_research_execution_rejects_unsafe_stage_twelve_approval(
    tmp_path, operation, approval_case
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    if operation == "validate":
        prepare_research_execution(project)
        contract = load_execution_contract(project.root)
        write_contract_bound_research_result(project, contract)
    approval_path = project.root / "approvals/stage-12.json"
    if approval_case == "symlink":
        outside = tmp_path / "outside-approval.json"
        outside.write_bytes(approval_path.read_bytes())
        approval_path.unlink()
        approval_path.symlink_to(outside)
    else:
        approval_bytes = approval_path.read_bytes()
        needle = b'"decision": "approve"'
        assert needle in approval_bytes
        approval_path.write_bytes(
            approval_bytes.replace(
                needle,
                b'"decision": "reject", "decision": "approve"',
                1,
            )
        )
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    events_before = (project.root / "evaluation/events.jsonl").read_bytes()

    with pytest.raises(ValueError, match="^execution_approval_invalid$"):
        if operation == "prepare":
            prepare_research_execution(project)
        else:
            validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "evaluation/events.jsonl").read_bytes() == events_before


def test_validate_research_result_rejects_fifo_promptly(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    result_path = project.root / "experiment/results.json"
    os.mkfifo(result_path)
    finished = threading.Event()
    errors = []

    def validate_fifo():
        try:
            validate_research_result(project, "experiment/results.json")
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=validate_fifo, daemon=True)
    worker.start()
    completed_promptly = finished.wait(1.0)
    if not completed_promptly:
        writer = os.open(result_path, os.O_WRONLY | os.O_NONBLOCK)
        os.close(writer)
        worker.join(timeout=1.0)

    assert completed_promptly
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "research_result_file_invalid"


def test_project_file_snapshot_still_reads_regular_files(tmp_path):
    root = tmp_path / "project"
    path = root / "data/input.bin"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"regular input\n")

    assert _read_project_file_snapshot(root, "data/input.bin") == b"regular input\n"


def test_validate_research_result_normalizes_decoder_recursion(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    result_path = project.root / "experiment/results.json"
    result_path.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    result_before = result_path.read_bytes()

    with pytest.raises(ValueError, match="^research_result_schema_invalid$"):
        validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert result_path.read_bytes() == result_before


_INVALID_RESULT_CASES = (
    ("extra_root", "research_result_schema_invalid"),
    ("missing_root", "research_result_schema_invalid"),
    ("extra_contract_key", "research_result_schema_invalid"),
    ("missing_contract_key", "research_result_schema_invalid"),
    ("extra_metric_key", "research_result_metrics_invalid"),
    ("missing_metric_key", "research_result_metrics_invalid"),
    ("extra_split_key", "research_result_split_invalid"),
    ("missing_split_key", "research_result_split_invalid"),
    ("extra_role_key", "research_result_split_invalid"),
    ("missing_role_key", "research_result_split_invalid"),
    ("extra_role_count_key", "research_result_split_invalid"),
    ("missing_role_count_key", "research_result_split_invalid"),
    ("extra_provenance_key", "research_result_provenance_mismatch"),
    ("missing_provenance_key", "research_result_provenance_mismatch"),
    ("extra_runtime_key", "research_result_schema_invalid"),
    ("missing_runtime_key", "research_result_schema_invalid"),
    ("float_schema_version", "research_result_schema_invalid"),
    ("nan_metric", "research_result_schema_invalid"),
    ("inf_runtime", "research_result_schema_invalid"),
    ("empty_metrics", "research_result_metrics_invalid"),
    ("partial_status", "research_result_schema_invalid"),
    ("failed_status", "research_result_schema_invalid"),
    ("development_flag", "development_result_not_registerable"),
    ("non_evidence_flag", "development_result_not_registerable"),
    ("wrong_project", "research_result_project_mismatch"),
    ("wrong_contract_id", "research_result_contract_mismatch"),
    ("wrong_contract_hash", "research_result_contract_mismatch"),
    ("changed_bindings", "research_result_provenance_mismatch"),
    ("changed_inputs", "research_result_provenance_mismatch"),
    ("negative_cell_count", "research_result_split_invalid"),
    ("missing_split_role", "research_result_split_invalid"),
    ("wrong_isolation_key", "research_result_split_invalid"),
    ("cell_overlap", "research_result_leakage_detected"),
    ("group_overlap", "research_result_leakage_detected"),
    ("leakage", "research_result_leakage_detected"),
    ("boolean_metric", "research_result_metrics_invalid"),
    ("empty_metric_name", "research_result_metrics_invalid"),
    ("negative_elapsed", "research_result_schema_invalid"),
    ("huge_elapsed", "research_result_schema_invalid"),
    ("elapsed_over_maximum", "research_result_schema_invalid"),
    ("zero_maximum", "research_result_schema_invalid"),
    ("budget_mismatch", "research_result_schema_invalid"),
)


def _mutate_research_result(payload, case):
    mutated = deepcopy(payload)
    if case == "extra_root":
        mutated["unexpected"] = True
    elif case == "missing_root":
        del mutated["status"]
    elif case == "extra_contract_key":
        mutated["execution_contract"]["unexpected"] = True
    elif case == "missing_contract_key":
        del mutated["execution_contract"]["sha256"]
    elif case == "extra_metric_key":
        mutated["metrics"]["primary"]["unexpected"] = True
    elif case == "missing_metric_key":
        del mutated["metrics"]["primary"]["unit"]
    elif case == "extra_split_key":
        mutated["split_summary"]["unexpected"] = True
    elif case == "missing_split_key":
        del mutated["split_summary"]["isolation_key"]
    elif case == "extra_role_key":
        mutated["split_summary"]["roles"]["holdout"] = {
            "cell_count": 1,
            "group_count": 1,
        }
    elif case == "missing_role_key":
        del mutated["split_summary"]["roles"]["test"]
    elif case == "extra_role_count_key":
        mutated["split_summary"]["roles"]["train"]["unexpected"] = 0
    elif case == "missing_role_count_key":
        del mutated["split_summary"]["roles"]["train"]["group_count"]
    elif case == "extra_provenance_key":
        mutated["provenance"]["unexpected"] = True
    elif case == "missing_provenance_key":
        del mutated["provenance"]["inputs"]
    elif case == "extra_runtime_key":
        mutated["runtime"]["unexpected"] = True
    elif case == "missing_runtime_key":
        del mutated["runtime"]["maximum_seconds"]
    elif case == "float_schema_version":
        mutated["schema_version"] = 1.0
    elif case == "nan_metric":
        mutated["metrics"]["primary"]["value"] = float("nan")
    elif case == "inf_runtime":
        mutated["runtime"]["elapsed_seconds"] = float("inf")
    elif case == "empty_metrics":
        mutated["metrics"] = {}
    elif case == "partial_status":
        mutated["status"] = "partial"
    elif case == "failed_status":
        mutated["status"] = "failed"
    elif case == "development_flag":
        mutated["development_only"] = True
    elif case == "non_evidence_flag":
        mutated["evidence_eligible"] = False
    elif case == "wrong_project":
        mutated["project_id"] = "other-project"
    elif case == "wrong_contract_id":
        mutated["execution_contract"]["contract_id"] = "0" * 64
    elif case == "wrong_contract_hash":
        mutated["execution_contract"]["sha256"] = "0" * 64
    elif case == "changed_bindings":
        mutated["provenance"]["bindings"]["design"]["sha256"] = "0" * 64
    elif case == "changed_inputs":
        mutated["provenance"]["inputs"][0]["sha256"] = "0" * 64
    elif case == "negative_cell_count":
        mutated["split_summary"]["roles"]["train"]["cell_count"] = -1
    elif case == "missing_split_role":
        del mutated["split_summary"]["roles"]["calibration"]
    elif case == "wrong_isolation_key":
        mutated["split_summary"]["isolation_key"] = "condition_id"
    elif case == "cell_overlap":
        mutated["split_summary"]["cell_overlap_count"] = 1
    elif case == "group_overlap":
        mutated["split_summary"]["group_overlap_count"] = 1
    elif case == "leakage":
        mutated["split_summary"]["leakage_count"] = 1
    elif case == "boolean_metric":
        mutated["metrics"]["primary"]["value"] = True
    elif case == "empty_metric_name":
        mutated["metrics"]["primary"]["name"] = ""
    elif case == "negative_elapsed":
        mutated["runtime"]["elapsed_seconds"] = -0.1
    elif case == "huge_elapsed":
        mutated["runtime"]["elapsed_seconds"] = 10**1000
    elif case == "elapsed_over_maximum":
        mutated["runtime"]["elapsed_seconds"] = 3.0
    elif case == "zero_maximum":
        mutated["runtime"]["maximum_seconds"] = 0
    elif case == "budget_mismatch":
        mutated["runtime"]["maximum_seconds"] = 3
    else:  # pragma: no cover - guarded by the literal parameter table
        raise AssertionError(case)
    return mutated


@pytest.mark.parametrize(
    ("case", "category"),
    _INVALID_RESULT_CASES,
    ids=[case for case, _category in _INVALID_RESULT_CASES],
)
def test_validate_research_result_rejects_invalid_payload_without_mutation(
    tmp_path, case, category
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_path.write_text(
        json.dumps(_mutate_research_result(payload, case), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    controls = {
        relative: (project.root / relative).read_bytes()
        for relative in (
            ".researchclaw/state.json",
            "evaluation/events.jsonl",
            "approvals/stage-12.json",
            "experiment/resources.json",
            "experiment/execution_contract.json",
            "experiment/results.json",
        )
    }

    with pytest.raises(ValueError, match=f"^{category}$"):
        validate_research_result(project, "experiment/results.json")

    assert {
        relative: (project.root / relative).read_bytes() for relative in controls
    } == controls


@pytest.mark.parametrize(
    ("case", "category"),
    _INVALID_RESULT_CASES,
    ids=[f"register-{case}" for case, _category in _INVALID_RESULT_CASES],
)
def test_register_research_result_records_bounded_failure_without_state_transition(
    tmp_path, case, category
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_path.write_text(
        json.dumps(_mutate_research_result(payload, case), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    controls = {
        relative: (project.root / relative).read_bytes()
        for relative in (
            ".researchclaw/state.json",
            "approvals/stage-12.json",
            "experiment/resources.json",
            "experiment/execution_contract.json",
            "experiment/results.json",
        )
    }

    with pytest.raises(ValueError, match=f"^{category}$"):
        register_research_result(project, "experiment/results.json")

    assert {
        relative: (project.root / relative).read_bytes() for relative in controls
    } == controls
    assert ResearchProject.open(project.root).state.current_stage == 12
    event = event_log_for(project.root).read_all()[-1]
    assert event.type == "research_result_registration_failed"
    assert event.payload["error_category"] == category
    assert set(event.payload) <= {
        "error_category",
        "contract_path",
        "contract_sha256",
        "result_path",
        "result_sha256",
    }


@pytest.mark.parametrize(
    ("result_path", "category"),
    (
        ("experiment/other.json", "research_result_file_invalid"),
        ("experiment/dev_results.json", "development_result_not_registerable"),
    ),
)
def test_register_research_result_records_bounded_path_failure(
    tmp_path, result_path, category
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match=f"^{category}$"):
        register_research_result(project, result_path)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    event = event_log_for(project.root).read_all()[-1]
    assert event.type == "research_result_registration_failed"
    assert event.payload["error_category"] == category
    assert set(event.payload) <= {
        "error_category",
        "contract_path",
        "contract_sha256",
        "result_path",
        "result_sha256",
    }


@pytest.mark.parametrize(
    ("result_path", "category"),
    (
        ("/tmp/results.json", "research_result_file_invalid"),
        ("../results.json", "research_result_file_invalid"),
        ("experiment/../results.json", "research_result_file_invalid"),
        ("experiment/other.json", "research_result_file_invalid"),
        ("experiment/dev_results.json", "development_result_not_registerable"),
    ),
)
def test_validate_research_result_rejects_noncanonical_paths_before_reading(
    tmp_path, result_path, category
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    events_before = (project.root / "evaluation/events.jsonl").read_bytes()

    with pytest.raises(ValueError, match=f"^{category}$"):
        validate_research_result(project, result_path)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "evaluation/events.jsonl").read_bytes() == events_before


@pytest.mark.parametrize("file_case", ("symlink", "directory"))
def test_validate_research_result_rejects_non_regular_result_files(tmp_path, file_case):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    result_path = project.root / "experiment/results.json"
    if file_case == "symlink":
        target = tmp_path / "outside.json"
        target.write_text("{}\n", encoding="utf-8")
        result_path.symlink_to(target)
    else:
        result_path.mkdir()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="^research_result_file_invalid$"):
        validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    if file_case == "symlink":
        assert result_path.is_symlink()
        assert target.read_bytes() == b"{}\n"
    else:
        assert result_path.is_dir()


def test_validate_research_result_rejects_duplicate_json_keys(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    result_path.write_bytes(
        result_path.read_bytes().replace(b'"status": "completed"', b'"status": "partial", "status": "completed"')
    )
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    result_before = result_path.read_bytes()

    with pytest.raises(ValueError, match="^research_result_schema_invalid$"):
        validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert result_path.read_bytes() == result_before


def test_validate_research_result_rejects_unregistered_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={
                path: artifact
                for path, artifact in current.state.artifacts.items()
                if path != EXECUTION_CONTRACT_PATH
            },
        )
    )
    write_contract_bound_research_result(project, contract)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="^execution_contract_invalid$"):
        validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_validate_research_result_rejects_stale_registered_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    input_path = project.root / contract["inputs"][0]["path"]
    input_path.write_bytes(b"newly approved research input\n")
    input_digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    resources_path = project.root / "experiment/resources.json"
    resources = json.loads(resources_path.read_text(encoding="utf-8"))
    resources["inputs"][0]["size_bytes"] = input_path.stat().st_size
    resources["inputs"][0]["sha256"] = input_digest
    resources["inputs"][0]["exists"] = True
    resources["inputs"][0]["is_regular_file"] = True
    resources_path.write_text(json.dumps(resources, sort_keys=True) + "\n", encoding="utf-8")
    resource_bytes = resources_path.read_bytes()
    resource_digest = hashlib.sha256(resource_bytes).hexdigest()
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={
                **current.state.artifacts,
                "experiment/resources.json": ArtifactRef(
                    path="experiment/resources.json",
                    sha256=resource_digest,
                    size=len(resource_bytes),
                ),
            },
        )
    )
    approval_path = project.root / "approvals/stage-12.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"]["experiment/resources.json"] = resource_digest
    approval_path.write_text(json.dumps(approval, sort_keys=True) + "\n", encoding="utf-8")
    write_contract_bound_research_result(project, contract)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="^execution_contract_stale$"):
        validate_research_result(project, "experiment/results.json")

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_writes_bound_contract_without_executing_project_code(tmp_path):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )
    marker = project.root / "project-code-executed"

    status = prepare_research_execution(project)

    contract_path = project.root / "experiment/execution_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert status.readiness == "ready_for_explicit_execution"
    assert status.approval_eligible is False
    assert status.command == contract["command"]
    assert status.result_path == "experiment/results.json"
    assert status.contract_sha256 == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert contract["project_id"] == project.state.project_id
    assert contract["prohibitions"]["researchclaw_managed_execution"] is False
    assert not marker.exists()


def test_marker_fixture_writes_only_when_project_code_is_run(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )
    marker = project.root / "project-code-executed"
    monkeypatch.chdir(project.root)

    with pytest.raises(SystemExit):
        runpy.run_path("experiment/code/main.py", run_name="__main__")

    assert marker.read_text(encoding="utf-8") == "executed"


def test_prepare_run_writes_the_exact_closed_contract_shape(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    prepare_research_execution(project)

    contract_path = project.root / EXECUTION_CONTRACT_PATH
    raw_contract = contract_path.read_bytes()
    contract = json.loads(raw_contract)
    assert raw_contract == json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert set(contract) == {
        "schema_version",
        "contract_id",
        "project_id",
        "created_at",
        "command",
        "result_path",
        "bindings",
        "inputs",
        "prohibitions",
        "result_template",
    }
    contract_id_payload = {
        key: contract[key]
        for key in (
            "project_id",
            "command",
            "result_path",
            "bindings",
            "inputs",
            "prohibitions",
            "result_template",
        )
    }
    assert contract["contract_id"] == hashlib.sha256(
        json.dumps(
            contract_id_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    expected_bindings = {
        name: {
            "path": path,
            "sha256": hashlib.sha256((project.root / path).read_bytes()).hexdigest(),
        }
        for name, path in {
            "design": "experiment/design.json",
            "package_manifest": "experiment/package_manifest.json",
            "config": "experiment/code/config.json",
            "resources": "experiment/resources.json",
        }.items()
    }
    manifest = json.loads(
        (project.root / "experiment/package_manifest.json").read_text(encoding="utf-8")
    )
    expected_bindings["package_files"] = sorted(
        [
            {"path": entry["path"], "sha256": entry["sha256"]}
            for entry in manifest["files"]
        ],
        key=lambda entry: entry["path"],
    )
    assert contract["bindings"] == expected_bindings
    input_bytes = (project.root / "data/input.csv").read_bytes()
    assert contract["inputs"] == [
        {
            "path": "data/input.csv",
            "size_bytes": len(input_bytes),
            "sha256": hashlib.sha256(input_bytes).hexdigest(),
            "license_status": "confirmed",
        }
    ]


@pytest.mark.parametrize(
    "relative_path",
    (
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
        "experiment/code/main.py",
        "data/input.csv",
    ),
)
def test_prepare_run_rejects_changed_approved_or_required_content(
    tmp_path, relative_path
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    contract_before = contract_path.read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    changed_path = project.root / relative_path
    changed_path.write_bytes(changed_path.read_bytes() + b"\nchanged")

    with pytest.raises(
        ValueError,
        match="execution_(approval_invalid|prerequisites_changed)",
    ):
        prepare_research_execution(project)

    assert contract_path.read_bytes() == contract_before
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_reuses_the_identical_current_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    first = prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    first_bytes = contract_path.read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    approval_before = (project.root / "approvals/stage-12.json").read_bytes()
    second = prepare_research_execution(project)

    assert contract_path.read_bytes() == first_bytes
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "approvals/stage-12.json").read_bytes() == approval_before
    assert second.contract_sha256 == first.contract_sha256
    assert second.to_dict() == first.to_dict()


@pytest.mark.parametrize(
    "tamper",
    (
        lambda payload: payload.replace(b'"created_at":', b'"created_at" :', 1),
        lambda payload: payload.replace(b"{", b'{"schema_version":1,', 1),
    ),
    ids=("whitespace", "duplicate-key"),
)
def test_prepare_run_rejects_tampered_registered_contract_bytes(tmp_path, tamper):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    contract_path.write_bytes(tamper(contract_path.read_bytes()))

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_rejects_canonical_contract_with_wrong_artifact_identity(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={
                **current.state.artifacts,
                EXECUTION_CONTRACT_PATH: ArtifactRef(
                    path=EXECUTION_CONTRACT_PATH,
                    sha256="0" * 64,
                    size=0,
                ),
            },
        )
    )

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)


def test_prepare_run_rejects_canonical_created_at_tampering(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["created_at"] = "2000-01-01T00:00:00+00:00"
    contract_path.write_bytes(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)


def test_prepare_run_rejects_preseeded_duplicate_key_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    contract_path.write_bytes(b'{"project_id":"first","project_id":"second"}')
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)

    assert contract_path.read_bytes() == b'{"project_id":"first","project_id":"second"}'
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_rejects_preseeded_canonical_candidate_without_artifact(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    candidate = _build_execution_contract(project)
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    preseeded_bytes = json.dumps(
        candidate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    contract_path.write_bytes(preseeded_bytes)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    approval_before = (project.root / "approvals/stage-12.json").read_bytes()

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)

    assert contract_path.read_bytes() == preseeded_bytes
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "approvals/stage-12.json").read_bytes() == approval_before


@pytest.mark.parametrize(
    "approval_case",
    ("missing", "rejected", "malformed", "non-current"),
)
def test_prepare_run_requires_a_current_explicit_approval(tmp_path, approval_case):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    approval_path = project.root / "approvals/stage-12.json"
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    if approval_case == "missing":
        approval_path.unlink()
    elif approval_case == "rejected":
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["decision"] = "reject"
        approval_path.write_text(json.dumps(approval), encoding="utf-8")
    elif approval_case == "malformed":
        approval_path.write_text("not-json", encoding="utf-8")
    else:
        (project.root / "experiment/design.json").write_bytes(b"changed")

    with pytest.raises(ValueError, match="execution_approval_invalid"):
        prepare_research_execution(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
