import hashlib
import json
import os
from pathlib import Path
import subprocess
from dataclasses import replace

import pytest

import researchclaw.core.refinement_execution as refinement_execution
from researchclaw.core.project import ResearchProject
from researchclaw.core.refinement import (
    load_refinement_session,
    register_refinement_candidate,
)
from researchclaw.core.refinement_execution import (
    REFINEMENT_SELF_TEST_REGISTRATION_ROOT,
    prepare_refinement_self_test,
    register_refinement_self_test,
)
from tests.codex_native.helpers import (
    immutable_stage_twelve_snapshot,
    write_refinement_candidate,
)
from tests.codex_native.test_refinement import refinement_project_with_refine_decision


def registered_candidate_project(path: Path):
    project = refinement_project_with_refine_decision(path)
    manifest = write_refinement_candidate(project)
    candidate = register_refinement_candidate(project, manifest)
    return ResearchProject.open(project.root), candidate


def run_candidate_self_test(project, candidate_id):
    preparation = prepare_refinement_self_test(project, candidate_id)
    completed = subprocess.run(
        preparation.argv,
        cwd=preparation.cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return preparation


def test_candidate_self_test_uses_verified_absolute_launcher_and_candidate_cwd(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")

    status = prepare_refinement_self_test(project, candidate.candidate_id)

    assert Path(status.argv[0]).is_absolute()
    assert status.cwd == str(
        project.root.resolve()
        / "refinement"
        / "candidates"
        / candidate.candidate_id
    )
    assert status.argv[1:5] == (
        "code/model.py",
        "--config",
        "tests/self_test_config.json",
        "--self-test",
    )
    assert status.argv[5] == "--refinement-self-test-context"
    context = json.loads(status.argv[6])
    assert context["candidate_id"] == candidate.candidate_id
    assert context["candidate_manifest"]["sha256"] == candidate.manifest_sha256
    assert context["preparation"]["path"] == status.preparation_path
    assert context["context_id"] == status.context_id
    assert context["context_sha256"] == status.context_sha256
    assert status.environment_fingerprint
    assert status.candidate_id == candidate.candidate_id
    assert status.candidate_manifest_sha256 == candidate.manifest_sha256
    assert status.package_contract_sha256 == candidate.package_contract_sha256


def test_candidate_self_test_registration_binds_context_without_consuming_run_budget(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    result_before = (project.root / "experiment/results.json").read_bytes()
    session_before = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )
    preparation = run_candidate_self_test(project, candidate.candidate_id)

    status = register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )

    reopened = ResearchProject.open(project.root)
    registration_path = (
        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/"
        f"{session_before['session_id']}/{candidate.candidate_id}.json"
    )
    registration = json.loads(
        (project.root / registration_path).read_text(encoding="utf-8")
    )
    report = json.loads(
        (project.root / preparation.report_path).read_text(encoding="utf-8")
    )
    assert status.next_action == "prepare_refinement_run"
    assert reopened.state.next_action == "prepare_refinement_run"
    assert preparation.report_path in reopened.state.artifacts
    assert registration_path in reopened.state.artifacts
    assert registration["schema_version"] == 1
    assert registration["project_id"] == project.state.project_id
    assert registration["session_id"] == session_before["session_id"]
    assert registration["candidate_id"] == candidate.candidate_id
    assert registration["producer"] == "implementation-agent"
    assert registration["environment_fingerprint"] == (
        preparation.environment_fingerprint
    )
    assert registration["candidate_manifest"]["sha256"] == (
        candidate.manifest_sha256
    )
    assert registration["council_decision"]["sha256"] == candidate.decision_sha256
    assert registration["evidence_packet"]["sha256"] == session_before[
        "evidence_packet"
    ]["sha256"]
    assert registration["package_contract"]["sha256"] == (
        candidate.package_contract_sha256
    )
    assert registration["self_test_report"]["path"] == preparation.report_path
    assert report["project_id"] == project.state.project_id
    assert report["session_id"] == session_before["session_id"]
    assert report["candidate_id"] == candidate.candidate_id
    assert report["producer"] == "implementation-agent"
    assert report["producer_role"] == "implementation"
    assert report["candidate_manifest"]["sha256"] == candidate.manifest_sha256
    assert report["council_decision"]["sha256"] == candidate.decision_sha256
    assert report["evidence_packet"] == session_before["evidence_packet"]
    assert report["baseline_manifest"] == registration["baseline_manifest"]
    assert report["candidate_files"] == registration["candidate_files"]
    assert report["config"] == registration["config"]
    assert report["created_at"].endswith("+00:00")
    assert json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["runs_used"] == session_before["runs_used"] == 0
    assert not (project.root / ".researchclaw/evidence/refinement-manifests").exists()
    assert immutable_stage_twelve_snapshot(reopened) == baseline_before
    assert (project.root / "experiment/results.json").read_bytes() == result_before


def test_prepare_candidate_self_test_revalidates_candidate_before_return(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    source = project.root / candidate.files[0].path
    source.write_bytes(source.read_bytes() + b"\n# tampered\n")

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        prepare_refinement_self_test(project, candidate.candidate_id)


def test_candidate_self_test_rejects_invalid_report_binding_without_side_effects(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    result_before = (project.root / "experiment/results.json").read_bytes()
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    report = project.root / preparation.report_path
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["package_contract"]["sha256"] = "0" * 64
    report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )

    assert ResearchProject.open(project.root).state == state_before
    assert immutable_stage_twelve_snapshot(project) == baseline_before
    assert (project.root / "experiment/results.json").read_bytes() == result_before


def test_candidate_self_test_registration_is_byte_identically_idempotent(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    first = register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    state_after_first = ResearchProject.open(project.root).state
    registration_ref = next(
        reference
        for path, reference in state_after_first.artifacts.items()
        if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
        and path.endswith(f"/{candidate.candidate_id}.json")
    )
    registration_bytes = (project.root / registration_ref.path).read_bytes()

    second = register_refinement_self_test(
        ResearchProject.open(project.root),
        candidate.candidate_id,
        preparation.report_path,
    )

    assert second == first
    assert ResearchProject.open(project.root).state == state_after_first
    assert (project.root / registration_ref.path).read_bytes() == registration_bytes


def test_candidate_self_test_registration_rejects_rewritten_registered_report(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    report = project.root / preparation.report_path
    report.write_bytes(report.read_bytes() + b" ")

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        register_refinement_self_test(
            ResearchProject.open(project.root),
            candidate.candidate_id,
            preparation.report_path,
        )


@pytest.mark.parametrize("interruption", ["after_record_write", "after_state_write"])
def test_candidate_self_test_registration_recovers_exact_record_orphan(
    tmp_path, monkeypatch, interruption
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    original_after_write = refinement_execution._after_anchored_registration_write
    original_publish = refinement_execution._publish_refinement_self_test_state

    def interrupt_after_record_write():
        raise RuntimeError("registration interrupted")

    def interrupt_after_state_write(*args):
        original_publish(*args)
        raise RuntimeError("registration interrupted")

    if interruption == "after_record_write":
        monkeypatch.setattr(
            refinement_execution,
            "_after_anchored_registration_write",
            interrupt_after_record_write,
        )
    else:
        monkeypatch.setattr(
            refinement_execution,
            "_publish_refinement_self_test_state",
            interrupt_after_state_write,
        )
    with pytest.raises(RuntimeError, match="registration interrupted"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )

    assert ResearchProject.open(project.root).state == state_before
    orphan = next(
        (project.root / REFINEMENT_SELF_TEST_REGISTRATION_ROOT).glob(
            f"*/{candidate.candidate_id}.json"
        )
    )
    orphan_bytes = orphan.read_bytes()

    monkeypatch.setattr(
        refinement_execution,
        "_after_anchored_registration_write",
        original_after_write,
    )
    monkeypatch.setattr(
        refinement_execution,
        "_publish_refinement_self_test_state",
        original_publish,
    )
    status = register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )

    assert status.next_action == "prepare_refinement_run"
    assert orphan.read_bytes() == orphan_bytes


def test_candidate_self_test_rejects_candidate_aba_during_report_validation(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    source = project.root / next(
        reference.path
        for reference in candidate.files
        if reference.path.endswith("/code/model.py")
    )
    original_bytes = source.read_bytes()
    original_validator = refinement_execution._validate_candidate_self_test_report

    def validate_then_restore(*args, **kwargs):
        validated = original_validator(*args, **kwargs)
        source.write_bytes(b"replacement")
        source.write_bytes(original_bytes)
        return validated

    monkeypatch.setattr(
        refinement_execution,
        "_validate_candidate_self_test_report",
        validate_then_restore,
    )

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_rejects_report_aba_during_validation(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    report = project.root / preparation.report_path
    original_bytes = report.read_bytes()
    original_validator = refinement_execution._validate_candidate_self_test_report

    def validate_then_restore(*args, **kwargs):
        validated = original_validator(*args, **kwargs)
        report.write_bytes(b"replacement")
        report.write_bytes(original_bytes)
        return validated

    monkeypatch.setattr(
        refinement_execution,
        "_validate_candidate_self_test_report",
        validate_then_restore,
    )

    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_rejects_environment_drift(tmp_path, monkeypatch):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    original_inspect = refinement_execution.inspect_execution_environment

    def drifted_environment(*args, **kwargs):
        environment = original_inspect(*args, **kwargs)
        return replace(environment, fingerprint="0" * 64)

    monkeypatch.setattr(
        refinement_execution, "inspect_execution_environment", drifted_environment
    )

    with pytest.raises(ValueError, match="refinement_self_test_environment_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_rejects_unknown_candidate_file(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    unknown = (
        project.root
        / "refinement"
        / "candidates"
        / candidate.candidate_id
        / "tests"
        / "unknown.json"
    )
    unknown.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refinement_candidate_manifest_open"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_rejects_hardlinked_report(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    report = project.root / preparation.report_path
    outside = tmp_path / "outside-report.json"
    outside.hardlink_to(report)

    with pytest.raises(
        ValueError,
        match="refinement_candidate_identity_changed|refinement_self_test_report_invalid",
    ):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_registration_leaves_no_execution_reservation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)

    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )

    paths = {
        path.relative_to(project.root).as_posix()
        for path in project.root.rglob("*")
        if path.is_file()
    }
    assert not any("reservation" in path for path in paths)
    assert not any("refinement-manifests" in path for path in paths)
    assert load_refinement_session(ResearchProject.open(project.root)).next_action == (
        "prepare_refinement_run"
    )


def test_candidate_self_test_rejects_partial_registered_state(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    report = project.root / preparation.report_path
    partial_ref = refinement_execution.ArtifactRef(
        preparation.report_path,
        hashlib.sha256(report.read_bytes()).hexdigest(),
        report.stat().st_size,
    )
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={**current.state.artifacts, preparation.report_path: partial_ref},
        )
    )

    with pytest.raises(
        ValueError, match="refinement_self_test_registration_recovery_invalid"
    ):
        register_refinement_self_test(
            ResearchProject.open(project.root),
            candidate.candidate_id,
            preparation.report_path,
        )


def test_candidate_self_test_report_cannot_replay_across_sessions(tmp_path):
    first, first_candidate = registered_candidate_project(tmp_path / "first")
    second, second_candidate = registered_candidate_project(tmp_path / "second")
    first_preparation = run_candidate_self_test(first, first_candidate.candidate_id)
    second_preparation = prepare_refinement_self_test(
        second, second_candidate.candidate_id
    )
    copied_report = first.root / first_preparation.report_path
    target_report = second.root / second_preparation.report_path
    target_report.write_bytes(copied_report.read_bytes())

    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            second, second_candidate.candidate_id, second_preparation.report_path
        )


def test_candidate_self_test_registration_rejects_parent_component_aba(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    registration_root = project.root / REFINEMENT_SELF_TEST_REGISTRATION_ROOT
    moved_root = project.root / ".researchclaw/refinement-self-tests-held"
    outside = tmp_path / "outside"
    outside.mkdir()
    swapped = False

    def swap_parent(*_args):
        nonlocal swapped
        registration_root.rename(moved_root)
        registration_root.symlink_to(outside, target_is_directory=True)
        swapped = True

    monkeypatch.setattr(
        refinement_execution,
        "_before_anchored_registration_leaf_create",
        swap_parent,
    )
    with pytest.raises(
        ValueError, match="refinement_self_test_registration_recovery_invalid"
    ):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )

    assert swapped
    assert not tuple(outside.iterdir())
    assert ResearchProject.open(project.root).state == state_before
    registration_root.unlink()
    moved_root.rename(registration_root)
    monkeypatch.setattr(
        refinement_execution,
        "_before_anchored_registration_leaf_create",
        lambda *_args: None,
    )
    assert register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    ).next_action == "prepare_refinement_run"


def test_candidate_self_test_registration_rejects_manifest_producer_aba(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    manifest = project.root / candidate.manifest_path
    original = manifest.read_bytes()

    def producer_aba(*_args):
        payload = json.loads(original)
        payload["producer"] = "reviewer-agent"
        manifest.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        manifest.write_bytes(original)

    monkeypatch.setattr(
        refinement_execution,
        "_before_refinement_self_test_publication",
        producer_aba,
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )
    assert ResearchProject.open(project.root).state == state_before


@pytest.mark.parametrize("drift_call", [2, 5])
def test_candidate_self_test_registration_rejects_late_environment_drift(
    tmp_path, monkeypatch, drift_call
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    original = refinement_execution._inspect_bound_environment
    calls = 0

    def drift_after_validation(*args, **kwargs):
        nonlocal calls
        calls += 1
        environment, launcher = original(*args, **kwargs)
        if calls == drift_call:
            environment = replace(environment, fingerprint="0" * 64)
        return environment, launcher

    monkeypatch.setattr(
        refinement_execution, "_inspect_bound_environment", drift_after_validation
    )
    with pytest.raises(ValueError, match="refinement_self_test_environment_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )
    assert ResearchProject.open(project.root).state == state_before


def test_candidate_self_test_registration_rejects_launcher_identity_drift(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    original = refinement_execution._inspect_bound_environment
    calls = 0

    def replace_launcher_identity(*args, **kwargs):
        nonlocal calls
        calls += 1
        environment, launcher = original(*args, **kwargs)
        if calls == 2:
            launcher = (
                *launcher[:-1],
                (*launcher[-1][:-1], int(launcher[-1][-1]) + 1),
            )
        return environment, launcher

    monkeypatch.setattr(
        refinement_execution,
        "_inspect_bound_environment",
        replace_launcher_identity,
    )
    with pytest.raises(ValueError, match="refinement_self_test_environment_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )
    assert ResearchProject.open(project.root).state == state_before


@pytest.mark.parametrize("artifact", ["report", "receipt"])
def test_registered_candidate_rejects_same_byte_artifact_replacement(
    tmp_path, artifact
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    reopened = ResearchProject.open(project.root)
    if artifact == "report":
        target = project.root / preparation.report_path
    else:
        target = project.root / next(
            path
            for path in reopened.state.artifacts
            if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
            and path.endswith(f"/{candidate.candidate_id}.json")
        )
    replacement = target.with_name(f".{target.name}.replacement")
    replacement.write_bytes(target.read_bytes())
    os.replace(replacement, target)

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        refinement_execution.revalidate_refinement_candidate(
            ResearchProject.open(project.root), candidate.candidate_id
        )


@pytest.mark.parametrize("loader", ["candidate", "session"])
def test_registered_candidate_reconstructs_receipt_semantics(
    tmp_path, loader
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    reopened = ResearchProject.open(project.root)
    registration_path = next(
        path
        for path in reopened.state.artifacts
        if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
        and path.endswith(f"/{candidate.candidate_id}.json")
    )
    registration = project.root / registration_path
    forged = json.loads(registration.read_text(encoding="utf-8"))
    forged["producer"] = "reviewer-agent"
    registration.write_text(
        json.dumps(forged, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    forged_bytes = registration.read_bytes()
    forged_ref = refinement_execution.ArtifactRef(
        registration_path, hashlib.sha256(forged_bytes).hexdigest(), len(forged_bytes)
    )
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={**writable.state.artifacts, registration_path: forged_ref},
        )
    )

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        if loader == "candidate":
            refinement_execution.revalidate_refinement_candidate(
                ResearchProject.open(project.root), candidate.candidate_id
            )
        else:
            load_refinement_session(ResearchProject.open(project.root))


@pytest.mark.parametrize("late_file", ["unknown", "report"])
def test_prepare_candidate_self_test_final_gate_rejects_late_tree_change(
    tmp_path, monkeypatch, late_file
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    candidate_root = (
        project.root / "refinement" / "candidates" / candidate.candidate_id
    )

    def insert_late_file(*_args):
        if late_file == "report":
            target = candidate_root / "package_metadata/self_test_report.json"
        else:
            target = candidate_root / "tests/late-unknown.json"
        target.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_self_test_preparation_environment",
        insert_late_file,
    )
    with pytest.raises(
        ValueError,
        match="refinement_self_test_report_exists|refinement_candidate_manifest_open",
    ):
        prepare_refinement_self_test(project, candidate.candidate_id)


def test_candidate_self_test_preparation_is_durable_and_idempotent(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    state_before = ResearchProject.open(project.root).state

    first = prepare_refinement_self_test(project, candidate.candidate_id)
    prepared_state = ResearchProject.open(project.root).state
    preparation_ref = prepared_state.artifacts[first.preparation_path]
    preparation_bytes = (project.root / first.preparation_path).read_bytes()
    preparation = json.loads(preparation_bytes)
    context = {
        key: value
        for key, value in preparation.items()
        if key not in {"context_id", "context_sha256"}
    }
    expected_hash = hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    second = prepare_refinement_self_test(
        ResearchProject.open(project.root), candidate.candidate_id
    )

    assert second == first
    assert preparation_ref.path == first.preparation_path
    assert preparation["schema_version"] == 1
    assert preparation["context_sha256"] == expected_hash == first.context_sha256
    assert preparation["context_id"] == first.context_id
    assert preparation["created_at"] in first.argv[-1]
    assert (project.root / first.preparation_path).read_bytes() == preparation_bytes
    assert ResearchProject.open(project.root).state == prepared_state
    assert json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["runs_used"] == 0
    assert prepared_state.next_action == state_before.next_action


def test_candidate_self_test_registration_rejects_deleted_preparation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    (project.root / preparation.preparation_path).unlink()

    with pytest.raises(ValueError, match="refinement_self_test_preparation_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_report_cannot_replay_from_old_preparation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    first = run_candidate_self_test(project, candidate.candidate_id)
    report_path = project.root / first.report_path
    first_report = report_path.read_bytes()
    report_path.unlink()
    (project.root / first.preparation_path).unlink()
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={
                path: reference
                for path, reference in current.state.artifacts.items()
                if path != first.preparation_path
            },
        )
    )

    second = prepare_refinement_self_test(
        ResearchProject.open(project.root), candidate.candidate_id
    )
    report_path.write_bytes(first_report)

    assert second.context_sha256 != first.context_sha256
    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, second.report_path
        )


def test_candidate_self_test_registration_rejects_report_timestamp_mutation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    report_path = project.root / preparation.report_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["created_at"] = "2026-09-02T00:00:00+00:00"
    report_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_registration_rejects_manifest_aba_after_receipt_write(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    manifest_path = project.root / candidate.manifest_path
    original = manifest_path.read_bytes()

    def producer_aba_after_write():
        payload = json.loads(original)
        payload["producer"] = "reviewer-agent"
        manifest_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        manifest_path.write_bytes(original)

    monkeypatch.setattr(
        refinement_execution,
        "_after_anchored_registration_write",
        producer_aba_after_write,
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )
    assert ResearchProject.open(project.root).state == state_before


def test_self_test_preparation_fsyncs_new_directories_before_leaf(tmp_path, monkeypatch):
    project, candidate = registered_candidate_project(tmp_path / "project")
    calls: list[str] = []
    original_fsync = refinement_execution.os.fsync

    def recording_fsync(descriptor):
        mode = os.fstat(descriptor).st_mode
        calls.append("directory" if refinement_execution.stat.S_ISDIR(mode) else "file")
        original_fsync(descriptor)

    monkeypatch.setattr(refinement_execution.os, "fsync", recording_fsync)

    prepare_refinement_self_test(project, candidate.candidate_id)

    first_file = calls.index("file")
    assert calls[:first_file].count("directory") >= 4
    assert calls[first_file + 1] == "directory"
