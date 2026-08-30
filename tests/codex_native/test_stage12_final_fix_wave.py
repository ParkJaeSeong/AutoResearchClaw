import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import researchclaw.core.research_execution as research_execution
import researchclaw.core.evidence_registration as evidence_registration
from researchclaw.codex.cli import main as cli_main
from researchclaw.core.development_execution import (
    run_development_experiment,
    validate_development_result,
)
from researchclaw.core.events import EvaluationEvent, EventLog, event_log_for
from researchclaw.core.handoff import build_handoff
from researchclaw.core.project import ResearchProject
from researchclaw.core.research_execution import (
    prepare_research_execution,
    register_research_result,
)
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    load_execution_contract,
    write_contract_bound_research_result,
    write_runnable_development_fixture,
)


def _leave_committing_registration(project, monkeypatch):
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    original_hook = evidence_registration._after_manifest_published

    def fail_after_manifest(_manifest):
        raise OSError("leave final-fix pending registration")

    monkeypatch.setattr(
        evidence_registration, "_after_manifest_published", fail_after_manifest
    )
    with pytest.raises(OSError, match="leave final-fix pending registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.setattr(
        evidence_registration, "_after_manifest_published", original_hook
    )
    return result_path


def _rewrite_pending_result_identity(project, result_path):
    result_bytes = result_path.read_bytes()
    result_sha256 = hashlib.sha256(result_bytes).hexdigest()
    pending_path = project.root / ".researchclaw/evidence/pending-registration.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending["result_sha256"] = result_sha256
    pending["result_size"] = len(result_bytes)
    pending["target_state"]["artifacts"]["experiment/results.json"].update(
        {"sha256": result_sha256, "size": len(result_bytes)}
    )
    pending["success_event"]["payload"]["result_sha256"] = result_sha256
    success_record = json.dumps(
        pending["success_event"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    pending["rollback_event"]["payload"].update(
        {
            "result_sha256": result_sha256,
            "registration_event_sha256": hashlib.sha256(success_record).hexdigest(),
        }
    )
    pending_path.write_text(
        json.dumps(pending, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return pending_path


def test_exact_prepared_command_produces_only_bound_result_then_registers(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status = prepare_research_execution(project)
    before = {
        path.relative_to(project.root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in project.root.rglob("*")
        if path.is_file()
    }

    completed = subprocess.run(
        status.argv,
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    result_path = project.root / "experiment/results.json"
    assert result_path.is_file()
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_payload["metrics"]["primary"]["value"] == 0.5
    after = {
        path.relative_to(project.root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in project.root.rglob("*")
        if path.is_file()
    }
    assert {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    } == {"experiment/results.json"}
    registered = register_research_result(project, "experiment/results.json")
    assert registered.current_stage == 13
    manifest = evidence_registration.load_evidence_manifest(
        project.root, registered.manifest_path
    )
    immutable_result = next(
        entry for entry in manifest["objects"] if entry["role"] == "result"
    )
    immutable_bytes = (
        project.root / immutable_result["object_path"]
    ).read_bytes()
    (project.root / "data/input.csv").write_bytes(b"mutable source changed\n")
    result_path.unlink()
    assert json.loads(immutable_bytes)["metrics"]["primary"]["value"] == 0.5
    assert build_handoff(ResearchProject.open(project.root)).current_stage == 13


def test_exact_prepared_command_rejects_bound_input_drift_without_output(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status = prepare_research_execution(project)
    (project.root / "data/input.csv").write_bytes(b"drifted before execution\n")
    before = {
        path.relative_to(project.root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in project.root.rglob("*")
        if path.is_file()
    }
    completed = subprocess.run(
        status.argv,
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    after = {
        path.relative_to(project.root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in project.root.rglob("*")
        if path.is_file()
    }
    assert completed.returncode != 0
    assert "execution input changed" in completed.stderr
    assert not (project.root / "experiment/results.json").exists()
    assert after == before


def test_recovery_ignores_mutable_result_drift_after_manifest(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    result_path = _leave_committing_registration(project, monkeypatch)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["development_only"] = True
    payload["evidence_eligible"] = False
    result_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    pending_path = project.root / ".researchclaw/evidence/pending-registration.json"

    handoff = build_handoff(project)

    reopened = ResearchProject.open(project.root)
    assert handoff.current_stage == 13
    assert reopened.state.current_stage == 13
    assert 12 in reopened.state.completed_stages
    assert not pending_path.exists()
    assert (
        len(research_execution.effective_research_result_registration_events(project))
        == 1
    )


def test_recovery_ignores_mutable_input_drift_after_manifest(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    (project.root / "data/input.csv").write_bytes(b"drifted after pending\n")

    handoff = build_handoff(project)

    reopened = ResearchProject.open(project.root)
    assert handoff.current_stage == 13
    assert reopened.state.current_stage == 13
    assert 12 in reopened.state.completed_stages
    assert not (
        project.root / ".researchclaw/evidence/pending-registration.json"
    ).exists()


def test_resume_handoff_recovers_pending_before_appending_resume_event(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    (project.root / "data/input.csv").write_bytes(b"drifted before resume\n")

    handoff = ResearchProject.open_readonly(project.root).build_handoff()

    assert handoff.current_stage == 13
    assert not (
        project.root / ".researchclaw/evidence/pending-registration.json"
    ).exists()
    assert event_log_for(project.root).read_all()[-1].type == "resume"


def test_pending_registration_blocks_development_commit_before_artifact_mutation(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    manifest = write_runnable_development_fixture(project)
    event_before = (project.root / "evaluation/events.jsonl").read_bytes()

    with pytest.raises(ValueError, match="^project_transaction_pending$"):
        run_development_experiment(
            ResearchProject.open_readonly(project.root),
            str(manifest.relative_to(project.root)),
        )

    assert not (project.root / "experiment/dev_results.json").exists()
    assert (project.root / "evaluation/events.jsonl").read_bytes() == event_before


def test_pending_registration_blocks_state_mutator_without_partial_state(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    current = ResearchProject.open_readonly(project.root)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="^project_transaction_pending$"):
        current.persist_state(replace(current.state, topic="must not persist"))

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_cli_normalizes_pending_development_validation_conflict(
    tmp_path, monkeypatch, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    manifest = write_runnable_development_fixture(project)
    run_development_experiment(
        ResearchProject.open_readonly(project.root),
        str(manifest.relative_to(project.root)),
    )
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    capsys.readouterr()

    exit_code = cli_main(
        [
            "execution",
            "validate-result",
            str(project.root),
            "--result",
            "experiment/dev_results.json",
            "--development",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "error: project_transaction_pending\n"


def test_pending_registration_concurrently_rejects_development_and_state_mutators(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    manifest = write_runnable_development_fixture(project)
    run_development_experiment(
        ResearchProject.open_readonly(project.root),
        str(manifest.relative_to(project.root)),
    )
    prepare_research_execution(project)
    _leave_committing_registration(project, monkeypatch)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    event_before = (project.root / "evaluation/events.jsonl").read_bytes()
    development_before = (project.root / "experiment/dev_results.json").read_bytes()

    def rerun():
        return run_development_experiment(
            ResearchProject.open_readonly(project.root),
            str(manifest.relative_to(project.root)),
        )

    def revalidate():
        return validate_development_result(
            ResearchProject.open_readonly(project.root),
            "experiment/dev_results.json",
        )

    def mutate_state():
        current = ResearchProject.open_readonly(project.root)
        return current.persist_state(replace(current.state, topic="must not persist"))

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(action) for action in (rerun, revalidate, mutate_state)
        ]
    for future in futures:
        with pytest.raises(ValueError, match="^project_transaction_pending$"):
            future.result()

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "evaluation/events.jsonl").read_bytes() == event_before
    assert (
        project.root / "experiment/dev_results.json"
    ).read_bytes() == development_before


def test_streaming_project_identity_hashes_large_sparse_input(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    input_path = root / "large.bin"
    with input_path.open("wb") as handle:
        handle.truncate(32 * 1024 * 1024)

    identity = research_execution._project_file_identity(root, "large.bin")

    digest = hashlib.sha256()
    zero_block = b"\0" * (1024 * 1024)
    for _ in range(32):
        digest.update(zero_block)
    assert identity.size == 32 * 1024 * 1024
    assert identity.sha256 == digest.hexdigest()


def test_oversized_result_fails_before_json_decode(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    result_path = project.root / "experiment/results.json"
    with result_path.open("wb") as handle:
        handle.truncate(research_execution.MAX_RESEARCH_RESULT_BYTES + 1)

    def decode_must_not_run(*_args, **_kwargs):
        raise AssertionError("oversized result reached JSON decoder")

    monkeypatch.setattr(
        research_execution, "_decode_research_result", decode_must_not_run
    )
    with pytest.raises(ValueError, match="^research_result_file_invalid$"):
        research_execution.validate_research_result(project, "experiment/results.json")


def test_registration_streams_existing_event_log_instead_of_snapshotting_it(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    original_snapshot = research_execution._read_project_file_snapshot

    def reject_whole_event_snapshot(root, relative_path, *args, **kwargs):
        if relative_path == "evaluation/events.jsonl":
            raise AssertionError("event log was loaded as one byte string")
        return original_snapshot(root, relative_path, *args, **kwargs)

    monkeypatch.setattr(
        research_execution,
        "_read_project_file_snapshot",
        reject_whole_event_snapshot,
    )

    assert (
        register_research_result(project, "experiment/results.json").current_stage == 13
    )


def test_prepare_streams_package_file_bindings_instead_of_snapshotting_them(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    original_snapshot = research_execution._read_project_file_snapshot

    def reject_package_file_snapshot(root, relative_path, *args, **kwargs):
        if relative_path == "experiment/code/main.py":
            raise AssertionError("package file was loaded as one byte string")
        return original_snapshot(root, relative_path, *args, **kwargs)

    monkeypatch.setattr(
        research_execution,
        "_read_project_file_snapshot",
        reject_package_file_snapshot,
    )

    assert prepare_research_execution(project).readiness == (
        "ready_for_explicit_execution"
    )


def test_oversized_contract_fails_before_contract_decode(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    with contract_path.open("wb") as handle:
        handle.truncate(research_execution.MAX_EXECUTION_CONTRACT_BYTES + 1)

    def decode_must_not_run(*_args, **_kwargs):
        raise AssertionError("oversized contract reached JSON decoder")

    monkeypatch.setattr(
        research_execution, "_decode_execution_contract", decode_must_not_run
    )
    with pytest.raises(ValueError, match="^execution_contract_invalid$"):
        research_execution.validate_research_result(project, "experiment/results.json")


def test_sparse_oversized_event_record_fails_without_whole_log_read(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    event_path = project.root / "evaluation/events.jsonl"
    with event_path.open("wb") as handle:
        handle.truncate(32 * 1024 * 1024)

    with pytest.raises(
        ValueError, match="^research_result_registration_recovery_invalid$"
    ):
        register_research_result(project, "experiment/results.json")

    assert ResearchProject.open(project.root).state.current_stage == 12
    assert not (
        project.root / ".researchclaw/evidence/pending-registration.json"
    ).exists()


def test_duplicate_key_event_is_rejected_before_registration_mutates_state(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    event = EvaluationEvent.create("forged", project.state.project_id, {})
    duplicate_record = (
        '{"payload":{},"payload":{},"project_id":'
        + json.dumps(project.state.project_id)
        + ',"schema_version":1,"timestamp":'
        + json.dumps(event.timestamp)
        + ',"type":"forged"}\n'
    ).encode("utf-8")
    with (project.root / "evaluation/events.jsonl").open("ab") as handle:
        handle.write(duplicate_record)

    with pytest.raises(
        ValueError, match="^research_result_registration_recovery_invalid$"
    ):
        register_research_result(project, "experiment/results.json")

    assert ResearchProject.open(project.root).state.current_stage == 12
    assert not (
        project.root / ".researchclaw/evidence/pending-registration.json"
    ).exists()


def test_oversized_event_is_rejected_before_any_record_bytes_are_written(tmp_path):
    project = ResearchProject.create(
        tmp_path / "project", topic="event cap", profile="materials_ai"
    )
    event_path = project.root / "evaluation/events.jsonl"
    before = event_path.read_bytes()

    with pytest.raises(ValueError, match="^event_record_too_large$"):
        event_log_for(project.root).append(
            EvaluationEvent.create(
                "oversized",
                project.state.project_id,
                {"payload": "x" * (128 * 1024)},
            )
        )

    assert event_path.read_bytes() == before


def test_stage_thirteen_grounding_streams_event_log_without_read_all(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    register_research_result(project, "experiment/results.json")

    def reject_read_all(_self):
        raise AssertionError("Stage-13 grounding loaded the complete event log")

    monkeypatch.setattr(EventLog, "read_all", reject_read_all)

    assert build_handoff(project).current_stage == 13


def test_prepare_run_recovers_owned_contract_commit_before_state_reference(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    original_record = research_execution._record_contract_artifact
    failed = False

    def fail_once(project, payload):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("interrupt after contract commit")
        return original_record(project, payload)

    monkeypatch.setattr(research_execution, "_record_contract_artifact", fail_once)
    with pytest.raises(OSError, match="interrupt after contract commit"):
        prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    committed = contract_path.read_bytes()
    assert (
        "experiment/execution_contract.json"
        not in ResearchProject.open(project.root).state.artifacts
    )

    recovered = prepare_research_execution(project)

    assert contract_path.read_bytes() == committed
    assert recovered.contract_sha256 == hashlib.sha256(committed).hexdigest()
    assert (
        "experiment/execution_contract.json"
        in ResearchProject.open(project.root).state.artifacts
    )
    assert not (
        project.root / ".researchclaw/execution-contract-preparation.pending.json"
    ).exists()
