import hashlib
import json
import os
import threading
from copy import deepcopy

import pytest

import researchclaw.core.evidence_registration as evidence_registration
import researchclaw.core.research_execution as research_execution
from researchclaw.core.evidence_registration import (
    EVIDENCE_PENDING_PATH,
    load_evidence_manifest,
    recover_pending_evidence_registration,
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
)


def _valid_result(root):
    project = build_approved_stage_twelve_project(root)
    prepare_research_execution(project)
    result = write_contract_bound_research_result(
        project, load_execution_contract(project.root)
    )
    return ResearchProject.open(project.root), result


def test_registered_stage_thirteen_uses_immutable_objects_after_source_changes(
    tmp_path,
):
    project, result = _valid_result(tmp_path / "project")

    status = register_research_result(project, "experiment/results.json")
    manifest_before = load_evidence_manifest(project.root, status.manifest_path)
    result_sha256 = hashlib.sha256(result.read_bytes()).hexdigest()

    (project.root / "data/input.csv").write_text("changed", encoding="utf-8")
    result.unlink()

    handoff = build_handoff(ResearchProject.open(project.root))
    assert handoff.current_stage == 13
    assert load_evidence_manifest(project.root, status.manifest_path) == manifest_before
    assert status.result_object_sha256 == result_sha256
    assert (project.root / ".researchclaw/evidence/objects" / result_sha256).is_file()


def test_mutation_after_validation_never_registers_bytes_under_old_identity(
    tmp_path, monkeypatch
):
    project, result = _valid_result(tmp_path / "project")
    original = evidence_registration._after_strict_validation

    def mutate_after_validation(validated):
        result.write_text('{"changed":true}\n', encoding="utf-8")
        original(validated)

    monkeypatch.setattr(
        evidence_registration, "_after_strict_validation", mutate_after_validation
    )

    with pytest.raises(ValueError, match="research_result_file_invalid"):
        register_research_result(project, "experiment/results.json")

    assert ResearchProject.open(project.root).state.current_stage == 12
    pending = project.root / EVIDENCE_PENDING_PATH
    assert not pending.exists()
    assert ResearchProject.open(project.root).state.current_stage == 12


def test_manifest_is_closed_and_binds_all_immutable_source_roles(tmp_path):
    project, _result = _valid_result(tmp_path / "project")

    status = register_research_result(project, "experiment/results.json")
    manifest = load_evidence_manifest(project.root, status.manifest_path)

    assert set(manifest) == {
        "schema_version",
        "registration_id",
        "project_id",
        "created_at",
        "approval",
        "execution_contract",
        "environment_fingerprint",
        "objects",
        "result",
        "metrics",
        "split_summary",
        "runtime",
    }
    roles = {entry["role"] for entry in manifest["objects"]}
    assert {"result", "execution_contract", "input", "package_file"} <= roles
    assert manifest["result"]["sha256"] == status.result_object_sha256
    assert not (project.root / EVIDENCE_PENDING_PATH).exists()
    assert json.dumps(manifest, allow_nan=False)


@pytest.mark.parametrize(
    ("seam", "expected_stage"),
    [
        ("_after_pending_persisted", 12),
        ("_after_object_published", 12),
        ("_after_manifest_published", 13),
        ("_after_state_saved", 13),
        ("_after_event_written", 13),
    ],
)
def test_each_registration_boundary_recovers_idempotently(
    tmp_path, monkeypatch, seam, expected_stage
):
    project, _result = _valid_result(tmp_path / "project")

    def interrupt(*_args):
        raise OSError(f"fault at {seam}")

    monkeypatch.setattr(evidence_registration, seam, interrupt)
    with pytest.raises(OSError, match="fault at"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    recover_pending_evidence_registration(project)
    state_after_first = ResearchProject.open(project.root).state
    second = recover_pending_evidence_registration(project)
    state_after_second = ResearchProject.open(project.root).state

    assert state_after_first == state_after_second
    assert state_after_second.current_stage == expected_stage
    assert second is None
    assert sum(
        event.type == "research_result_registered"
        for event in event_log_for(project.root).read_all()
    ) == (1 if expected_stage == 13 else 0)


@pytest.mark.parametrize("prefix_length", (1, 8, 32, "complete"))
def test_partial_registration_event_is_repaired_and_recovered(
    tmp_path, monkeypatch, prefix_length
):
    project, _result = _valid_result(tmp_path / "project")
    original = EventLog._write_record
    interrupted = False

    def partial_then_fail(self, descriptor, event):
        nonlocal interrupted
        if event.type == "research_result_registered" and not interrupted:
            interrupted = True
            record = EventLog._bounded_record(event)
            length = len(record) if prefix_length == "complete" else prefix_length
            os.write(descriptor, record[:length])
            os.fsync(descriptor)
            raise OSError("partial event")
        return original(self, descriptor, event)

    monkeypatch.setattr(EventLog, "_write_record", partial_then_fail)
    with pytest.raises(OSError, match="partial event"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    recovered = recover_pending_evidence_registration(project)
    assert recovered is not None
    assert ResearchProject.open(project.root).state.current_stage == 13
    assert (
        sum(
            event.type == "research_result_registered"
            for event in event_log_for(project.root).read_all()
        )
        == 1
    )


@pytest.mark.parametrize("fault_seam", ("_after_state_saved", "_after_event_written"))
def test_recovery_durably_aborts_if_immutable_object_is_corrupt_after_promotion(
    tmp_path, monkeypatch, fault_seam
):
    project, _result = _valid_result(tmp_path / "project")

    def interrupt(*_args):
        raise OSError("stop after promotion boundary")

    monkeypatch.setattr(evidence_registration, fault_seam, interrupt)
    with pytest.raises(OSError, match="stop after promotion boundary"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending_path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    result_sha = pending["manifest"]["result"]["sha256"]
    object_path = project.root / ".researchclaw/evidence/objects" / result_sha
    object_path.chmod(0o600)
    object_path.write_bytes(b"corrupt immutable object")

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        recover_pending_evidence_registration(project)

    assert not pending_path.exists()
    assert ResearchProject.open(project.root).state.current_stage == 12
    assert (
        research_execution.effective_research_result_registration_events(project)
        == ()
    )
    assert sum(
        event.type == "research_result_registration_rolled_back"
        for event in event_log_for(project.root).read_all()
    ) == (1 if fault_seam == "_after_event_written" else 0)

    assert recover_pending_evidence_registration(project) is None
    assert ResearchProject.open(project.root).state.current_stage == 12


@pytest.mark.parametrize(
    "abort_fault",
    (
        "_after_abort_intent_persisted",
        "_after_abort_rollback_event",
        "_after_abort_state_restored",
    ),
)
def test_integrity_abort_recovers_each_durable_boundary_exactly_once(
    tmp_path, monkeypatch, abort_fault
):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_event():
        raise OSError("leave committed registration")

    monkeypatch.setattr(
        evidence_registration, "_after_event_written", stop_after_event
    )
    with pytest.raises(OSError, match="leave committed registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending_path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    object_path = (
        project.root
        / ".researchclaw/evidence/objects"
        / pending["manifest"]["result"]["sha256"]
    )
    object_path.chmod(0o600)
    object_path.write_bytes(b"corrupt")

    def interrupt_abort(*_args):
        raise OSError(f"fault at {abort_fault}")

    monkeypatch.setattr(evidence_registration, abort_fault, interrupt_abort)
    with pytest.raises(OSError, match="fault at"):
        recover_pending_evidence_registration(project)
    monkeypatch.undo()

    assert recover_pending_evidence_registration(project) is None
    assert recover_pending_evidence_registration(project) is None
    assert ResearchProject.open(project.root).state.current_stage == 12
    assert (
        research_execution.effective_research_result_registration_events(project)
        == ()
    )
    events = event_log_for(project.root).read_all()
    assert sum(
        event.type == "research_result_registration_rolled_back"
        for event in events
    ) == 1


@pytest.mark.parametrize("prefix_length", (1, 8, "complete"))
def test_torn_rollback_event_recovers_at_its_owned_boundary(
    tmp_path, monkeypatch, prefix_length
):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_event():
        raise OSError("leave committed registration")

    monkeypatch.setattr(
        evidence_registration, "_after_event_written", stop_after_event
    )
    with pytest.raises(OSError, match="leave committed registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending = json.loads(
        (project.root / EVIDENCE_PENDING_PATH).read_text(encoding="utf-8")
    )
    object_path = (
        project.root
        / ".researchclaw/evidence/objects"
        / pending["manifest"]["result"]["sha256"]
    )
    object_path.chmod(0o600)
    object_path.write_bytes(b"corrupt")
    original = EventLog._write_record

    def tear_rollback(self, descriptor, event):
        if event.type == "research_result_registration_rolled_back":
            record = EventLog._bounded_record(event)
            length = len(record) if prefix_length == "complete" else prefix_length
            os.write(descriptor, record[:length])
            os.fsync(descriptor)
            raise OSError("torn rollback")
        return original(descriptor, event)

    monkeypatch.setattr(EventLog, "_write_record", tear_rollback)
    with pytest.raises(OSError, match="torn rollback"):
        recover_pending_evidence_registration(project)
    monkeypatch.undo()

    assert recover_pending_evidence_registration(project) is None
    assert ResearchProject.open(project.root).state.current_stage == 12
    assert (
        research_execution.effective_research_result_registration_events(project)
        == ()
    )
    assert sum(
        event.type == "research_result_registration_rolled_back"
        for event in event_log_for(project.root).read_all()
    ) == 1


def test_rollback_repair_accepts_every_exact_owned_prefix(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_event():
        raise OSError("leave committed registration")

    monkeypatch.setattr(
        evidence_registration, "_after_event_written", stop_after_event
    )
    with pytest.raises(OSError, match="leave committed registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending = json.loads(
        (project.root / EVIDENCE_PENDING_PATH).read_text(encoding="utf-8")
    )
    event_path = project.root / "evaluation/events.jsonl"
    base = event_path.read_bytes()
    pending["rollback_offset"] = len(base)
    rollback = EvaluationEvent.from_dict(pending["rollback_event"])
    record = EventLog._bounded_record(rollback)

    for prefix_length in range(1, len(record)):
        event_path.write_bytes(base + record[:prefix_length])
        evidence_registration._repair_owned_partial_rollback(project, pending)
        assert event_path.read_bytes() == base


def test_torn_rollback_recovery_never_truncates_foreign_bytes(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_event():
        raise OSError("leave committed registration")

    monkeypatch.setattr(
        evidence_registration, "_after_event_written", stop_after_event
    )
    with pytest.raises(OSError, match="leave committed registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()
    pending = json.loads(
        (project.root / EVIDENCE_PENDING_PATH).read_text(encoding="utf-8")
    )
    object_path = (
        project.root
        / ".researchclaw/evidence/objects"
        / pending["manifest"]["result"]["sha256"]
    )
    object_path.chmod(0o600)
    object_path.write_bytes(b"corrupt")

    def foreign_then_fail(self, descriptor, event):
        assert event.type == "research_result_registration_rolled_back"
        os.write(descriptor, b"foreign-tail")
        os.fsync(descriptor)
        raise OSError("foreign rollback boundary")

    monkeypatch.setattr(EventLog, "_write_record", foreign_then_fail)
    with pytest.raises(OSError, match="foreign rollback boundary"):
        recover_pending_evidence_registration(project)
    monkeypatch.undo()
    event_path = project.root / "evaluation/events.jsonl"
    before = event_path.read_bytes()

    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        recover_pending_evidence_registration(project)
    assert event_path.read_bytes() == before


def test_missing_manifest_after_success_event_is_neutralized(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_event():
        raise OSError("leave committed registration")

    monkeypatch.setattr(
        evidence_registration, "_after_event_written", stop_after_event
    )
    with pytest.raises(OSError, match="leave committed registration"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending_path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    (project.root / pending["manifest_path"]).unlink()

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        recover_pending_evidence_registration(project)

    assert not pending_path.exists()
    assert ResearchProject.open(project.root).state.current_stage == 12
    assert (
        research_execution.effective_research_result_registration_events(project)
        == ()
    )


def test_manifest_path_replacement_during_registered_status_fails_closed(
    tmp_path, monkeypatch
):
    project, _result = _valid_result(tmp_path / "project")
    status = register_research_result(project, "experiment/results.json")
    path = project.root / status.manifest_path

    def replace_after_snapshot(_snapshot):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["metrics"]["primary"]["value"] = 7.5
        replacement = path.with_suffix(".replacement")
        replacement.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(replacement, path)

    monkeypatch.setattr(
        evidence_registration, "_after_manifest_snapshot", replace_after_snapshot
    )
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        register_research_result(project, "experiment/results.json")


def test_manifest_path_replacement_during_recovery_fails_closed(
    tmp_path, monkeypatch
):
    project, _result = _valid_result(tmp_path / "project")

    def stop_after_manifest(_manifest):
        raise OSError("leave recovery pending")

    monkeypatch.setattr(
        evidence_registration, "_after_manifest_published", stop_after_manifest
    )
    with pytest.raises(OSError, match="leave recovery pending"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    pending_path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    path = project.root / pending["manifest_path"]

    def replace_after_snapshot(_snapshot):
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)

    monkeypatch.setattr(
        evidence_registration, "_after_manifest_snapshot", replace_after_snapshot
    )
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        recover_pending_evidence_registration(project)

    assert not pending_path.exists()
    assert ResearchProject.open(project.root).state.current_stage == 12


def test_registered_status_rejects_symlinked_manifest_ancestor(tmp_path):
    project, _result = _valid_result(tmp_path / "project")
    register_research_result(project, "experiment/results.json")
    manifests = project.root / ".researchclaw/evidence/manifests"
    external = tmp_path / "external-manifests"
    manifests.rename(external)
    manifests.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        register_research_result(project, "experiment/results.json")


def test_manifest_ancestor_symlink_race_after_snapshot_fails_closed(
    tmp_path, monkeypatch
):
    project, _result = _valid_result(tmp_path / "project")
    register_research_result(project, "experiment/results.json")
    manifests = project.root / ".researchclaw/evidence/manifests"
    external = tmp_path / "external-manifests"

    def replace_ancestor_after_snapshot(_snapshot):
        manifests.rename(external)
        manifests.symlink_to(external, target_is_directory=True)

    monkeypatch.setattr(
        evidence_registration,
        "_after_manifest_snapshot",
        replace_ancestor_after_snapshot,
    )
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        register_research_result(project, "experiment/results.json")


def test_manifest_revalidation_never_chases_a_growing_eof(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")
    status = register_research_result(project, "experiment/results.json")
    snapshot = evidence_registration._read_manifest_snapshot(
        project.root, status.manifest_path
    )
    path = project.root / status.manifest_path
    original_read = os.read
    calls = 0

    def grow_before_each_read(descriptor, count):
        nonlocal calls
        calls += 1
        if calls > 3:
            raise AssertionError("revalidation followed a moving EOF")
        with path.open("ab") as handle:
            handle.write(b"x" * 4096)
            handle.flush()
            os.fsync(handle.fileno())
        return original_read(descriptor, count)

    monkeypatch.setattr(os, "read", grow_before_each_read)
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        evidence_registration._revalidate_manifest_path(project.root, snapshot)
    assert calls <= 2


def test_registered_status_rejects_valid_json_manifest_rewrite(tmp_path):
    project, _result = _valid_result(tmp_path / "project")
    status = register_research_result(project, "experiment/results.json")
    manifest_path = project.root / status.manifest_path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["metrics"]["primary"]["value"] = 9.5
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        register_research_result(project, "experiment/results.json")


@pytest.mark.parametrize(
    "tamper",
    (
        "registration_id",
        "project_id",
        "prior_state",
        "prior_state_extra",
        "event_metric_count",
        "source_identity",
        "published_object_path",
        "nested_extra",
    ),
)
def test_pending_semantic_tampering_fails_closed(tmp_path, monkeypatch, tamper):
    project, _result = _valid_result(tmp_path / "project")

    def interrupt(_manifest):
        raise OSError("leave pending")

    monkeypatch.setattr(evidence_registration, "_after_manifest_published", interrupt)
    with pytest.raises(OSError, match="leave pending"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(path.read_text(encoding="utf-8"))
    changed = deepcopy(pending)
    if tamper == "registration_id":
        changed["registration_id"] = "0" * 32
    elif tamper == "project_id":
        changed["project_id"] = "forged-project"
    elif tamper == "prior_state":
        changed["prior_state"]["topic"] = "forged topic"
        changed["prior_state_sha256"] = evidence_registration._hash(
            changed["prior_state"]
        )
    elif tamper == "prior_state_extra":
        changed["prior_state"]["extra"] = "must not be dropped"
        changed["prior_state_sha256"] = evidence_registration._hash(
            changed["prior_state"]
        )
    elif tamper == "event_metric_count":
        changed["event"]["payload"]["metric_count"] = 99
        changed["event_sha256"] = evidence_registration._hash(changed["event"])
    elif tamper == "source_identity":
        changed["sources"][0]["expected_sha256"] = "0" * 64
    elif tamper == "published_object_path":
        changed["objects"][0]["path"] = ".researchclaw/evidence/objects/" + "0" * 64
    else:
        changed["event"]["payload"]["extra"] = True
        changed["event_sha256"] = evidence_registration._hash(changed["event"])
    path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        recover_pending_evidence_registration(project)


@pytest.mark.parametrize(
    ("event_name", "mutation"),
    (
        ("event", "top_extra"),
        ("rollback_event", "top_extra"),
        ("event", "nested_extra"),
        ("rollback_event", "nested_extra"),
        ("event", "missing_timestamp"),
        ("rollback_event", "wrong_payload_type"),
        ("event", "boolean_schema_version"),
        ("rollback_event", "boolean_schema_version"),
    ),
)
def test_pending_events_have_closed_exact_schemas(
    tmp_path, monkeypatch, event_name, mutation
):
    project, _result = _valid_result(tmp_path / "project")

    def interrupt(_manifest):
        raise OSError("leave pending")

    monkeypatch.setattr(evidence_registration, "_after_manifest_published", interrupt)
    with pytest.raises(OSError, match="leave pending"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()

    path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(path.read_text(encoding="utf-8"))
    event = pending[event_name]
    if mutation == "top_extra":
        event["extra"] = "must not be dropped"
    elif mutation == "nested_extra":
        event["payload"]["extra"] = "must not be dropped"
    elif mutation == "missing_timestamp":
        del event["timestamp"]
    elif mutation == "boolean_schema_version":
        event["schema_version"] = True
    else:
        event["payload"] = []
    pending[f"{event_name}_sha256"] = evidence_registration._hash(event)
    path.write_text(json.dumps(pending, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        recover_pending_evidence_registration(project)


def test_pending_journal_schema_version_rejects_boolean(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")

    def interrupt(_manifest):
        raise OSError("leave pending")

    monkeypatch.setattr(evidence_registration, "_after_manifest_published", interrupt)
    with pytest.raises(OSError, match="leave pending"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()
    path = project.root / EVIDENCE_PENDING_PATH
    pending = json.loads(path.read_text(encoding="utf-8"))
    pending["schema_version"] = True
    path.write_text(json.dumps(pending, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        recover_pending_evidence_registration(project)


def test_pending_size_cap_is_checked_before_atomic_write(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")
    called = False

    def atomic_write_must_not_run(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        evidence_registration, "atomic_write_json", atomic_write_must_not_run
    )
    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        evidence_registration._persist_pending(
            project, {"oversized": "x" * (256 * 1024)}
        )
    assert called is False
    assert not (project.root / EVIDENCE_PENDING_PATH).exists()


def test_recovery_preserves_unrelated_event_tail_at_reserved_offset(
    tmp_path, monkeypatch
):
    project, _result = _valid_result(tmp_path / "project")
    event_path = project.root / "evaluation/events.jsonl"

    def write_unrelated_then_fail(self, event, *, expected_offset):
        if event.type == "research_result_registered":
            with self.path.open("ab") as handle:
                handle.write(b"unrelated-tail")
                handle.flush()
                os.fsync(handle.fileno())
            raise OSError("unrelated tail")
        raise AssertionError("unexpected event")

    monkeypatch.setattr(EventLog, "append_locked", write_unrelated_then_fail)
    with pytest.raises(OSError, match="unrelated tail"):
        register_research_result(project, "experiment/results.json")
    before = event_path.read_bytes()
    monkeypatch.undo()

    with pytest.raises(ValueError, match="evidence_registration_interrupted"):
        recover_pending_evidence_registration(project)
    assert event_path.read_bytes() == before


def test_concurrent_registration_returns_one_immutable_identity(tmp_path):
    project, _result = _valid_result(tmp_path / "project")
    statuses = []
    errors = []

    def register():
        try:
            statuses.append(
                register_research_result(project, "experiment/results.json")
            )
        except BaseException as error:
            errors.append(error)

    workers = [threading.Thread(target=register) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)

    assert errors == []
    assert len(statuses) == 2
    assert statuses[0].registration_id == statuses[1].registration_id
    assert (
        sum(
            event.type == "research_result_registered"
            for event in event_log_for(project.root).read_all()
        )
        == 1
    )
