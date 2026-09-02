import hashlib
import json
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
    candidate_root = manifest.parent.parent
    source_path = candidate_root / "code/model.py"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        "experiment/package_contract.json", "package_metadata/package_contract.json"
    )
    source = source.replace(
        "experiment/package_manifest.json", "package_metadata/package_manifest.json"
    )
    source = source.replace("experiment/code/main.py", "code/model.py")
    source_path.write_text(source, encoding="utf-8")
    package_manifest_path = candidate_root / "package_metadata/package_manifest.json"
    package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    package_manifest["files"][0]["sha256"] = hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    package_manifest_path.write_text(
        json.dumps(package_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    candidate_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    by_path = {entry["path"]: entry for entry in candidate_manifest["files"]}
    for relative_path in (
        "refinement/candidates/candidate-001/code/model.py",
        "refinement/candidates/candidate-001/package_metadata/package_manifest.json",
    ):
        payload = (project.root / relative_path).read_bytes()
        by_path[relative_path]["sha256"] = hashlib.sha256(payload).hexdigest()
        by_path[relative_path]["size"] = len(payload)
    manifest.write_text(
        json.dumps(candidate_manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
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
    assert status.argv[1:] == (
        "code/model.py",
        "--config",
        "tests/self_test_config.json",
        "--self-test",
    )
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
    state_before = ResearchProject.open(project.root).state
    preparation = run_candidate_self_test(project, candidate.candidate_id)
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
    original_write = refinement_execution._write_exclusive
    original_publish = refinement_execution._publish_refinement_self_test_state

    def interrupt_after_record_write(*args):
        original_write(*args)
        raise RuntimeError("registration interrupted")

    def interrupt_after_state_write(*args):
        original_publish(*args)
        raise RuntimeError("registration interrupted")

    if interruption == "after_record_write":
        monkeypatch.setattr(
            refinement_execution, "_write_exclusive", interrupt_after_record_write
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
        (project.root / REFINEMENT_SELF_TEST_REGISTRATION_ROOT).glob("*/*.json")
    )
    orphan_bytes = orphan.read_bytes()

    monkeypatch.setattr(
        refinement_execution,
        "_write_exclusive",
        original_write,
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
