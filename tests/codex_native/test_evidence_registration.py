import hashlib
import json
import os
import threading

import pytest

import researchclaw.core.evidence_registration as evidence_registration
from researchclaw.core.evidence_registration import (
    EVIDENCE_PENDING_PATH,
    load_evidence_manifest,
    recover_pending_evidence_registration,
)
from researchclaw.core.events import EventLog, event_log_for
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

    with pytest.raises(ValueError, match="evidence source identity mismatch"):
        register_research_result(project, "experiment/results.json")

    assert ResearchProject.open(project.root).state.current_stage == 12
    pending = project.root / EVIDENCE_PENDING_PATH
    assert pending.is_file()
    recovered = recover_pending_evidence_registration(project)
    assert recovered is None
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


def test_partial_registration_event_is_repaired_and_recovered(tmp_path, monkeypatch):
    project, _result = _valid_result(tmp_path / "project")
    original = EventLog._write_record
    interrupted = False

    def partial_then_fail(self, descriptor, event):
        nonlocal interrupted
        if event.type == "research_result_registered" and not interrupted:
            interrupted = True
            record = EventLog._bounded_record(event)
            os.write(descriptor, record[: len(record) // 2])
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
