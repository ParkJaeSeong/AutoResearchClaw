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
    finalize_refinement,
    load_refinement_session,
    prepare_refinement_session,
    register_refinement_candidate,
    register_refinement_decision,
    register_refinement_rebuttals,
)
from researchclaw.core.refinement_execution import (
    REFINEMENT_EVIDENCE_MANIFEST_ROOT,
    REFINEMENT_RUN_REGISTRATION_ROOT,
    REFINEMENT_SELF_TEST_REGISTRATION_ROOT,
    prepare_refinement_run,
    prepare_refinement_self_test,
    register_refinement_result,
    register_refinement_self_test,
)
from tests.codex_native.helpers import (
    build_stage_thirteen_project,
    immutable_stage_twelve_snapshot,
    write_refinement_candidate,
)
from tests.codex_native.test_refinement import (
    _packet_artifact,
    refinement_project_with_refine_decision,
    register_all_assessments,
    register_one_assessment,
    valid_envelope,
    write_final_decision,
    write_valid_decision,
    write_valid_rebuttals,
)


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


def self_tested_candidate_project(path: Path):
    project, candidate = registered_candidate_project(path)
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    return ResearchProject.open(project.root), candidate


def self_tested_candidate_project_with_envelope(
    path: Path, *, maximum_runs: int, maximum_wall_seconds: int
):
    project = build_stage_thirteen_project(path)
    envelope = valid_envelope()
    envelope["maximum_runs"] = maximum_runs
    envelope["maximum_wall_seconds"] = maximum_wall_seconds
    envelope["maximum_candidate_seconds"] = min(
        envelope["maximum_candidate_seconds"], maximum_wall_seconds
    )
    prepare_refinement_session(project, envelope)
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    manifest = write_refinement_candidate(project)
    candidate = register_refinement_candidate(project, manifest)
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    return ResearchProject.open(project.root), candidate


def mutate_on_nth_run_inventory_scan(
    monkeypatch, run_root: Path, *, scan_number: int, mutation
):
    original_scandir = os.scandir
    matching_scans = 0

    class MutatingScandir:
        def __init__(self, iterator):
            self.iterator = iterator
            self.mutated = False

        def __enter__(self):
            self.iterator.__enter__()
            return self

        def __exit__(self, *args):
            return self.iterator.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            try:
                return next(self.iterator)
            except StopIteration:
                if not self.mutated:
                    self.mutated = True
                    mutation()
                raise

    def mutating_scandir(path):
        nonlocal matching_scans
        iterator = original_scandir(path)
        if isinstance(path, int) and run_root.exists():
            opened = os.fstat(path)
            expected = run_root.stat()
            if (opened.st_dev, opened.st_ino) == (expected.st_dev, expected.st_ino):
                matching_scans += 1
                if matching_scans == scan_number:
                    return MutatingScandir(iterator)
        return iterator

    monkeypatch.setattr(refinement_execution.os, "scandir", mutating_scandir)


def test_prepare_refinement_run_reserves_exact_authoritative_contract_without_execution(
    tmp_path,
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    baseline_result_before = (project.root / "experiment/results.json").read_bytes()
    candidate_result = project.root / "refinement/candidates/candidate-001/results.json"
    session = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )

    status = prepare_refinement_run(project, candidate.candidate_id)

    assert status.run_id == "run-001"
    assert Path(status.argv[0]).is_absolute()
    assert status.argv[1:4] == ("code/model.py", "--config", "config/config.json")
    assert status.argv[-2:] == (
        "--refinement-run-context",
        str((project.root / status.contract_path).resolve()),
    )
    assert status.cwd == str(
        project.root.resolve() / "refinement/candidates/candidate-001"
    )
    assert status.intent_path == (
        f".researchclaw/refinement-runs/{session['session_id']}/run-001.intent.json"
    )
    assert status.contract_path == (
        f".researchclaw/refinement-runs/{session['session_id']}/run-001.contract.json"
    )
    assert status.result_path == "refinement/candidates/candidate-001/results.json"
    contract_bytes = (project.root / status.contract_path).read_bytes()
    contract = json.loads(contract_bytes)
    assert set(contract) == {
        "schema_version",
        "contract_id",
        "project_id",
        "session_id",
        "candidate_id",
        "run_id",
        "producer",
        "producer_role",
        "created_at",
        "reservation",
        "contract_filesystem_identity",
        "candidate_manifest",
        "candidate_files",
        "package_contract",
        "package_manifest",
        "entry_point",
        "self_test",
        "council_decision",
        "evidence_packet",
        "baseline_manifest",
        "baseline_result",
        "allowed_inputs",
        "allowed_change_roots",
        "binding_filesystem_identities",
        "execution",
        "envelope",
        "expected_result",
    }
    assert contract["schema_version"] == 1
    assert contract["project_id"] == project.state.project_id
    assert contract["session_id"] == session["session_id"]
    assert contract["candidate_id"] == candidate.candidate_id
    assert contract["run_id"] == status.run_id
    assert contract["producer"] == "implementation-agent"
    assert contract["producer_role"] == "implementation"
    assert contract["candidate_manifest"]["sha256"] == candidate.manifest_sha256
    assert contract["council_decision"]["sha256"] == candidate.decision_sha256
    assert contract["evidence_packet"] == session["evidence_packet"]
    assert contract["allowed_inputs"][0]["path"] == "data/input.csv"
    assert contract["execution"]["argv"] == list(status.argv)
    assert contract["execution"]["cwd"] == status.cwd
    assert contract["execution"]["input_bindings"] == [
        {
            **contract["allowed_inputs"][0],
            "absolute_path": str((project.root / contract["allowed_inputs"][0]["path"]).resolve()),
        }
    ]
    assert contract["execution"]["environment_fingerprint"] == (
        status.environment_fingerprint
    )
    assert contract["expected_result"]["path"] == status.result_path
    assert hashlib.sha256(contract_bytes).hexdigest() == status.contract_sha256
    assert ResearchProject.open(project.root).state.next_action == (
        "register_refinement_result"
    )
    session_status = load_refinement_session(ResearchProject.open(project.root))
    assert session_status.runs_used == 1
    assert session_status.wall_seconds_used == 0.0
    assert session_status.phase == "awaiting_candidate_result"
    assert not candidate_result.exists()
    assert immutable_stage_twelve_snapshot(project) == baseline_before
    assert (project.root / "experiment/results.json").read_bytes() == (
        baseline_result_before
    )


def test_context_bound_refinement_argv_produces_registrable_result(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")

    run = prepare_refinement_run(project, candidate.candidate_id)
    completed = subprocess.run(
        run.argv,
        cwd=run.cwd,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    contract_path = project.root / run.contract_path
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    result_path = project.root / run.result_path
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert run.argv[-2:] == ("--refinement-run-context", str(contract_path.resolve()))
    assert result["execution_contract"] == {
        "path": run.contract_path,
        "contract_id": contract["contract_id"],
        "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "size": len(contract_path.read_bytes()),
    }

    registered = register_refinement_result(
        ResearchProject.open(project.root), candidate.candidate_id, run.result_path
    )

    assert registered.run_id == run.run_id
    assert registered.result_path == run.result_path


def test_candidate_metric_changes_with_a_different_bound_input(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    run = prepare_refinement_run(project, candidate.candidate_id)
    completed = subprocess.run(run.argv, cwd=run.cwd, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result_path = project.root / run.result_path
    first_metric = json.loads(result_path.read_text(encoding="utf-8"))["metrics"]["primary"]["value"]

    context_path = project.root / run.contract_path
    alternate_context = json.loads(context_path.read_text(encoding="utf-8"))
    binding = alternate_context["execution"]["input_bindings"][0]
    alternate_input = tmp_path / "alternate-input.json"
    alternate_bytes = Path(binding["absolute_path"]).read_bytes() + b" changed"
    alternate_input.write_bytes(alternate_bytes)
    alternate_path = context_path.with_name("alternate.contract.json")
    alternate_relative = alternate_path.relative_to(project.root).as_posix()
    binding.update(
        absolute_path=str(alternate_input.resolve()),
        sha256=hashlib.sha256(alternate_bytes).hexdigest(),
        size=len(alternate_bytes),
    )
    alternate_context["execution"]["run_contract_path"] = alternate_relative
    alternate_context["execution"]["argv"][-1] = str(alternate_path.resolve())
    alternate_path.write_text(json.dumps(alternate_context, sort_keys=True), encoding="utf-8")
    alternate_argv = (*run.argv[:-1], str(alternate_path.resolve()))
    completed = subprocess.run(
        alternate_argv, cwd=run.cwd, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    second_metric = json.loads(result_path.read_text(encoding="utf-8"))["metrics"]["primary"]["value"]

    assert second_metric != first_metric


def test_prepare_refinement_run_is_idempotent_for_the_exact_pending_reservation(
    tmp_path,
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    first = prepare_refinement_run(project, candidate.candidate_id)
    state_after_first = ResearchProject.open(project.root).state
    intent_bytes = (project.root / first.intent_path).read_bytes()
    contract_bytes = (project.root / first.contract_path).read_bytes()

    second = prepare_refinement_run(
        ResearchProject.open(project.root), candidate.candidate_id
    )

    assert second == first
    assert ResearchProject.open(project.root).state == state_after_first
    assert (project.root / second.intent_path).read_bytes() == intent_bytes
    assert (project.root / second.contract_path).read_bytes() == contract_bytes
    assert not tuple(
        (project.root / REFINEMENT_RUN_REGISTRATION_ROOT).glob("*/run-002.*")
    )


def test_prepare_refinement_run_recovers_exact_intent_only_reservation(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")

    def interrupt_after_intent():
        raise RuntimeError("intent reserved")

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_intent_publication",
        interrupt_after_intent,
    )
    with pytest.raises(RuntimeError, match="intent reserved"):
        prepare_refinement_run(project, candidate.candidate_id)

    pending = ResearchProject.open(project.root)
    intent_paths = [
        path
        for path in pending.state.artifacts
        if path.startswith(f"{REFINEMENT_RUN_REGISTRATION_ROOT}/")
    ]
    assert len(intent_paths) == 1
    assert intent_paths[0].endswith("/run-001.intent.json")
    assert pending.state.next_action == "prepare_refinement_run"
    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_intent_publication",
        lambda: None,
    )

    recovered = prepare_refinement_run(pending, candidate.candidate_id)

    assert recovered.run_id == "run-001"
    assert recovered.intent_path == intent_paths[0]
    assert ResearchProject.open(project.root).state.next_action == (
        "register_refinement_result"
    )


def test_prepare_refinement_run_rescans_closed_inventory_after_intent_publication(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    run_root = project.root / REFINEMENT_RUN_REGISTRATION_ROOT / session_id
    unexpected = run_root / "unexpected.json"

    def inject_unknown_record():
        unexpected.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_intent_publication",
        inject_unknown_record,
    )

    with pytest.raises(ValueError, match="^refinement_run_reservation_invalid$"):
        prepare_refinement_run(project, candidate.candidate_id)

    pending = ResearchProject.open(project.root)
    assert pending.state.next_action == "prepare_refinement_run"
    assert len(tuple(run_root.glob("run-001.intent.json"))) == 1
    assert not (run_root / "run-001.contract.json").exists()
    unexpected.unlink()
    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_intent_publication",
        lambda: None,
    )

    recovered = prepare_refinement_run(pending, candidate.candidate_id)

    assert recovered.run_id == "run-001"
    assert recovered.next_action == "register_refinement_result"


def test_prepare_refinement_run_rejects_unknown_inserted_during_inventory_scan(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    run_root = project.root / REFINEMENT_RUN_REGISTRATION_ROOT / session_id
    unexpected = run_root / "unexpected.json"
    mutate_on_nth_run_inventory_scan(
        monkeypatch,
        run_root,
        scan_number=3,
        mutation=lambda: unexpected.write_text("{}", encoding="utf-8"),
    )

    with pytest.raises(ValueError, match="^refinement_run_reservation_invalid$"):
        prepare_refinement_run(project, candidate.candidate_id)

    assert unexpected.exists()
    unexpected.unlink()
    recovered = prepare_refinement_run(
        ResearchProject.open(project.root), candidate.candidate_id
    )
    assert recovered.run_id == "run-001"
    assert recovered.next_action == "register_refinement_result"


def test_prepare_refinement_run_rejects_session_directory_aba_during_inventory_scan(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    run_root = project.root / REFINEMENT_RUN_REGISTRATION_ROOT / session_id
    renamed = run_root.with_name(f"{session_id}.renamed")
    mutations = []

    def rename_away_and_back():
        run_root.rename(renamed)
        renamed.rename(run_root)
        mutations.append("renamed")

    mutate_on_nth_run_inventory_scan(
        monkeypatch,
        run_root,
        scan_number=3,
        mutation=rename_away_and_back,
    )

    with pytest.raises(ValueError, match="^refinement_run_reservation_invalid$"):
        prepare_refinement_run(project, candidate.candidate_id)

    assert run_root.is_dir()
    assert not renamed.exists()
    assert mutations == ["renamed"]
    recovered = prepare_refinement_run(
        ResearchProject.open(project.root), candidate.candidate_id
    )
    assert recovered.run_id == "run-001"
    assert recovered.next_action == "register_refinement_result"


def test_prepare_refinement_run_recovers_exact_contract_only_publication(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")

    def interrupt_after_contract():
        raise RuntimeError("contract durable")

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_contract_write",
        interrupt_after_contract,
    )
    with pytest.raises(RuntimeError, match="contract durable"):
        prepare_refinement_run(project, candidate.candidate_id)

    pending = ResearchProject.open(project.root)
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    contract_path = (
        project.root
        / REFINEMENT_RUN_REGISTRATION_ROOT
        / session_id
        / "run-001.contract.json"
    )
    contract_bytes = contract_path.read_bytes()
    contract_identity = (contract_path.stat().st_dev, contract_path.stat().st_ino)
    assert contract_path.relative_to(project.root).as_posix() not in pending.state.artifacts
    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_run_contract_write",
        lambda: None,
    )

    recovered = prepare_refinement_run(pending, candidate.candidate_id)

    assert recovered.run_id == "run-001"
    assert contract_path.read_bytes() == contract_bytes
    assert (contract_path.stat().st_dev, contract_path.stat().st_ino) == (
        contract_identity
    )
    assert ResearchProject.open(project.root).state.artifacts[
        recovered.contract_path
    ].sha256 == recovered.contract_sha256


def test_prepare_refinement_run_rejects_expired_session_without_reserving_slot(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )
    created_at = refinement_execution.datetime.fromisoformat(session["created_at"])
    monkeypatch.setattr(
        refinement_execution,
        "_utc_now",
        lambda: created_at + refinement_execution.timedelta(seconds=121),
    )

    with pytest.raises(ValueError, match="^refinement_run_wall_time_exhausted$"):
        prepare_refinement_run(project, candidate.candidate_id)

    assert not (project.root / REFINEMENT_RUN_REGISTRATION_ROOT).exists()


def test_refinement_run_reservation_is_capped_by_actual_session_deadline(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )
    created_at = refinement_execution.datetime.fromisoformat(session["created_at"])
    deadline = created_at + refinement_execution.timedelta(seconds=120)
    monkeypatch.setattr(
        refinement_execution,
        "_utc_now",
        lambda: deadline - refinement_execution.timedelta(seconds=1),
    )

    preparation = prepare_refinement_run(project, candidate.candidate_id)
    contract = json.loads((project.root / preparation.contract_path).read_bytes())

    assert contract["envelope"]["session_deadline"] == deadline.isoformat()
    assert contract["envelope"]["deadline_seconds_remaining"] == 1.0
    assert contract["envelope"]["reserved_maximum_seconds"] == 1
    result_path = write_refinement_result(
        project, preparation, elapsed_seconds=1.0
    )
    registered = register_refinement_result(
        ResearchProject.open(project.root),
        candidate.candidate_id,
        result_path.relative_to(project.root),
    )
    assert registered.wall_seconds_used == 1.0


def test_refinement_run_samples_deadline_after_authority_revalidation(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )
    created_at = refinement_execution.datetime.fromisoformat(session["created_at"])
    deadline = created_at + refinement_execution.timedelta(seconds=120)
    current_time = [deadline - refinement_execution.timedelta(seconds=61)]
    original_inspect = refinement_execution._inspect_bound_environment

    def inspect_then_advance(package):
        inspected = original_inspect(package)
        current_time[0] = deadline - refinement_execution.timedelta(seconds=1)
        return inspected

    monkeypatch.setattr(refinement_execution, "_utc_now", lambda: current_time[0])
    monkeypatch.setattr(
        refinement_execution,
        "_inspect_bound_environment",
        inspect_then_advance,
    )

    preparation = prepare_refinement_run(project, candidate.candidate_id)
    contract = json.loads((project.root / preparation.contract_path).read_bytes())

    assert contract["envelope"]["deadline_seconds_remaining"] == 1.0
    assert contract["envelope"]["reserved_maximum_seconds"] == 1


@pytest.mark.parametrize("unsafe_kind", ["unknown", "symlink", "hardlink"])
def test_prepare_refinement_run_rejects_unknown_or_unsafe_reservation_records(
    tmp_path, unsafe_kind
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    reservation_root = (
        project.root / REFINEMENT_RUN_REGISTRATION_ROOT / session_id
    )
    reservation_root.mkdir(parents=True)
    if unsafe_kind == "unknown":
        (reservation_root / "unexpected.json").write_text("{}", encoding="utf-8")
    elif unsafe_kind == "symlink":
        (reservation_root / "run-001.intent.json").symlink_to(
            project.root / "refinement/session.json"
        )
    else:
        os.link(
            project.root / "refinement/session.json",
            reservation_root / "run-001.intent.json",
        )

    with pytest.raises(ValueError, match="^refinement_run_reservation_invalid$"):
        prepare_refinement_run(project, candidate.candidate_id)

    assert ResearchProject.open(project.root).state.next_action == (
        "prepare_refinement_run"
    )


def write_refinement_result(
    project: ResearchProject,
    status,
    *,
    elapsed_seconds: float = 1.0,
    metric_value: float = -999.0,
):
    contract_bytes = (project.root / status.contract_path).read_bytes()
    contract = json.loads(contract_bytes)
    execution = contract["execution"]
    payload = {
        "schema_version": 1,
        "project_id": contract["project_id"],
        "session_id": contract["session_id"],
        "candidate_id": contract["candidate_id"],
        "run_id": contract["run_id"],
        "producer": contract["producer"],
        "producer_role": contract["producer_role"],
        "created_at": "2026-09-03T00:00:00+00:00",
        "execution_contract": {
            "path": status.contract_path,
            "contract_id": contract["contract_id"],
            "sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "size": len(contract_bytes),
        },
        "development_only": False,
        "evidence_eligible": True,
        "status": "completed",
        "metrics": {
            "primary": {
                "name": "mae",
                "value": metric_value,
                "unit": "absolute_error",
            }
        },
        "split_summary": {
            "isolation_key": "cell_id",
            "roles": {
                "train": {"cell_count": 6, "group_count": 3},
                "validation": {"cell_count": 2, "group_count": 1},
                "calibration": {"cell_count": 2, "group_count": 1},
                "test": {"cell_count": 4, "group_count": 2},
            },
            "cell_overlap_count": 0,
            "group_overlap_count": 0,
            "leakage_count": 0,
        },
        "provenance": {
            "candidate_manifest": contract["candidate_manifest"],
            "candidate_files": contract["candidate_files"],
            "package_contract": contract["package_contract"],
            "package_manifest": contract["package_manifest"],
            "entry_point": contract["entry_point"],
            "self_test": contract["self_test"],
            "council_decision": contract["council_decision"],
            "evidence_packet": contract["evidence_packet"],
            "baseline_manifest": contract["baseline_manifest"],
            "baseline_result": contract["baseline_result"],
            "inputs": contract["allowed_inputs"],
            "environment_fingerprint": execution["environment_fingerprint"],
            "execution_environment": execution["environment"],
            "launcher_identity": execution["launcher_identity"],
        },
        "runtime": {
            "elapsed_seconds": elapsed_seconds,
            "maximum_seconds": contract["envelope"]["reserved_maximum_seconds"],
        },
    }
    target = project.root / status.result_path
    target.write_bytes(_canonical_bytes(payload))
    return target


def test_register_refinement_result_publishes_only_refinement_evidence_and_deliberates(
    tmp_path,
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    baseline_result_before = (project.root / "experiment/results.json").read_bytes()
    baseline_manifests_before = sorted(
        path
        for path in project.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    )
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    result_path = write_refinement_result(project, preparation, metric_value=-999.0)
    result_bytes = result_path.read_bytes()

    status = register_refinement_result(
        ResearchProject.open(project.root), candidate.candidate_id, preparation.result_path
    )

    expected_manifest = (
        f"{REFINEMENT_EVIDENCE_MANIFEST_ROOT}/"
        f"{json.loads((project.root / 'refinement/session.json').read_text())['session_id']}/"
        f"{candidate.candidate_id}/{preparation.run_id}.json"
    )
    reopened = ResearchProject.open(project.root)
    assert status.run_id == "run-001"
    assert status.evidence_manifest_path == expected_manifest
    assert status.runs_used == 1
    assert status.wall_seconds_used == 1.0
    assert status.next_action == "register_refinement_assessment"
    assert reopened.state.next_action == "register_refinement_assessment"
    assert reopened.state.artifacts[preparation.result_path].sha256 == hashlib.sha256(
        result_bytes
    ).hexdigest()
    manifest = json.loads((project.root / expected_manifest).read_bytes())
    result_object = next(item for item in manifest["objects"] if item["role"] == "result")
    assert (project.root / result_object["object_path"]).read_bytes() == result_bytes
    assert sorted(
        path
        for path in reopened.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    ) == baseline_manifests_before
    assert not any(
        path.startswith(".researchclaw/evidence/manifests/")
        and path.endswith(f"{preparation.run_id}.json")
        for path in reopened.state.artifacts
    )
    assert immutable_stage_twelve_snapshot(reopened) == baseline_before
    assert (project.root / "experiment/results.json").read_bytes() == baseline_result_before
    session_status = load_refinement_session(reopened)
    assert session_status.runs_used == 1
    assert session_status.next_action == "register_refinement_assessment"
    assert session_status.phase == "awaiting_independent_assessments"


def test_finalize_select_candidate_retains_verified_refinement_evidence(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    registered = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    result = ResearchProject.open(project.root).state.artifacts[registered.result_path]
    evaluated = [_packet_artifact(project), {
        "path": result.path,
        "sha256": result.sha256,
        "size": result.size,
    }]
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role, artifacts=evaluated)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision_path = write_final_decision(project, "select_candidate")

    finalize_refinement(project, decision_path)

    reopened = ResearchProject.open(project.root)
    selection = json.loads((project.root / "refinement/final_selection.json").read_text())
    retained = {item["path"] for item in selection["retained_evidence"]}
    assert selection["selected_candidate_id"] == candidate.candidate_id
    assert registered.evidence_manifest_path in retained
    assert immutable_stage_twelve_snapshot(reopened) == baseline_before


def test_finalize_select_candidate_requires_council_to_reference_its_result(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    registered = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    result = ResearchProject.open(project.root).state.artifacts[registered.result_path]
    evaluated = [_packet_artifact(project), {
        "path": result.path,
        "sha256": result.sha256,
        "size": result.size,
    }]
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role, artifacts=evaluated)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision_path = write_final_decision(
        project, "select_candidate", include_selected_evidence=False
    )

    with pytest.raises(ValueError, match="refinement_finalization_evidence_invalid"):
        finalize_refinement(project, decision_path)
    assert ResearchProject.open(project.root).state.current_stage == 13


def test_register_refinement_result_is_byte_identically_idempotent(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    first = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    state_after_first = ResearchProject.open(project.root).state
    manifest_bytes = (project.root / first.evidence_manifest_path).read_bytes()

    second = register_refinement_result(
        ResearchProject.open(project.root), candidate.candidate_id, preparation.result_path
    )

    assert second == first
    assert ResearchProject.open(project.root).state == state_after_first
    assert (project.root / second.evidence_manifest_path).read_bytes() == manifest_bytes
    assert len(
        tuple((project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).rglob("run-*.json"))
    ) == 1


def test_two_candidate_runs_complete_and_retry_with_historical_counters(tmp_path):
    project, first_candidate = self_tested_candidate_project(tmp_path / "project")
    first_preparation = prepare_refinement_run(project, first_candidate.candidate_id)
    write_refinement_result(project, first_preparation, elapsed_seconds=1.0)
    first = register_refinement_result(
        project, first_candidate.candidate_id, first_preparation.result_path
    )
    first_result = ResearchProject.open(project.root).state.artifacts[
        first.result_path
    ]
    evaluated = [
        _packet_artifact(ResearchProject.open(project.root)),
        {
            "path": first_result.path,
            "sha256": first_result.sha256,
            "size": first_result.size,
        },
    ]
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role, artifacts=evaluated)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(
        project, write_valid_decision(project, candidate_id="candidate-002")
    )
    second_manifest = write_refinement_candidate(
        ResearchProject.open(project.root), candidate_id="candidate-002"
    )
    second_candidate = register_refinement_candidate(project, second_manifest)
    second_self_test = run_candidate_self_test(project, second_candidate.candidate_id)
    register_refinement_self_test(
        project, second_candidate.candidate_id, second_self_test.report_path
    )
    second_preparation = prepare_refinement_run(
        ResearchProject.open(project.root), second_candidate.candidate_id
    )
    write_refinement_result(project, second_preparation, elapsed_seconds=2.0)

    second = register_refinement_result(
        ResearchProject.open(project.root),
        second_candidate.candidate_id,
        second_preparation.result_path,
    )
    state_after_second = ResearchProject.open(project.root).state
    repeated = register_refinement_result(
        ResearchProject.open(project.root),
        second_candidate.candidate_id,
        second_preparation.result_path,
    )

    assert second == repeated
    assert second.run_id == "run-002"
    assert second.runs_used == 2
    assert second.wall_seconds_used == 3.0
    assert ResearchProject.open(project.root).state == state_after_second
    assert state_after_second.artifacts[first.result_path] == first_result
    assert len(
        tuple((project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).rglob("run-*.json"))
    ) == 2
    session = load_refinement_session(ResearchProject.open(project.root))
    assert session.runs_used == 2
    assert session.wall_seconds_used == 3.0
    assert session.next_action == "register_refinement_assessment"


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda result: result.update(extra=True), "refinement_result_schema_invalid"),
        (lambda result: result.update(status="running"), "refinement_result_schema_invalid"),
        (lambda result: result.update(created_at="not-a-time"), "refinement_result_schema_invalid"),
        (
            lambda result: result["execution_contract"].update(contract_id="0" * 64),
            "refinement_result_contract_mismatch",
        ),
        (
            lambda result: result["provenance"]["inputs"][0].update(sha256="0" * 64),
            "refinement_result_provenance_mismatch",
        ),
        (
            lambda result: result["metrics"]["primary"].update(value=float("nan")),
            "refinement_result_metrics_invalid",
        ),
        (
            lambda result: result["runtime"].update(elapsed_seconds=-1.0),
            "refinement_result_runtime_invalid",
        ),
        (
            lambda result: result["runtime"].update(elapsed_seconds=61.0),
            "refinement_result_runtime_invalid",
        ),
    ],
    ids=[
        "unknown-field",
        "incomplete-status",
        "invalid-created-at",
        "contract",
        "input-provenance",
        "nonfinite-metric",
        "negative-runtime",
        "runtime-over-reservation",
    ],
)
def test_register_refinement_result_rejects_schema_metric_runtime_or_provenance_tampering(
    tmp_path, mutation, error
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    result_path = write_refinement_result(project, preparation)
    result = json.loads(result_path.read_bytes())
    mutation(result)
    result_path.write_bytes(_canonical_bytes(result))
    state_before = ResearchProject.open(project.root).state

    with pytest.raises(ValueError, match=f"^{error}$"):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )

    assert ResearchProject.open(project.root).state == state_before
    assert not (project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).exists()


@pytest.mark.parametrize("seam", ["intent", "manifest", "state"])
def test_register_refinement_result_recovers_exact_partial_publication(
    tmp_path, monkeypatch, seam
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)

    hook = {
        "intent": "_after_refinement_result_intent_publication",
        "manifest": "_after_refinement_evidence_manifest_publication",
        "state": "_after_refinement_result_state_publication",
    }[seam]

    def interrupt():
        raise RuntimeError(f"{seam} interrupted")

    monkeypatch.setattr(refinement_execution, hook, interrupt, raising=False)
    with pytest.raises(RuntimeError, match=f"{seam} interrupted"):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )
    monkeypatch.setattr(refinement_execution, hook, lambda: None, raising=False)

    recovered = register_refinement_result(
        ResearchProject.open(project.root), candidate.candidate_id, preparation.result_path
    )

    assert recovered.run_id == "run-001"
    assert recovered.runs_used == 1
    assert recovered.wall_seconds_used == 1.0
    assert len(
        tuple((project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).rglob("run-*.json"))
    ) == 1


def test_register_refinement_result_recovers_intent_write_before_state_publication(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    original_persist_state = ResearchProject.persist_state
    interrupted = False

    def interrupt_intent_state(self, state):
        nonlocal interrupted
        newly_registered = tuple(
            path
            for path in state.artifacts
            if path.endswith(".registration.intent.json")
            and path not in self.state.artifacts
        )
        if newly_registered and not interrupted:
            interrupted = True
            raise RuntimeError("intent state interrupted")
        return original_persist_state(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", interrupt_intent_state)
    with pytest.raises(RuntimeError, match="intent state interrupted"):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )
    monkeypatch.setattr(ResearchProject, "persist_state", original_persist_state)
    pending = ResearchProject.open(project.root)
    orphaned = tuple(
        path
        for path in (
            project.root / preparation.intent_path
        ).parent.glob("run-*.registration.intent.json")
    )
    assert len(orphaned) == 1
    assert not any(
        path.endswith(".registration.intent.json") for path in pending.state.artifacts
    )

    recovered = register_refinement_result(
        pending, candidate.candidate_id, preparation.result_path
    )

    assert recovered.run_id == "run-001"
    assert recovered.next_action == "register_refinement_assessment"


def test_register_refinement_result_recovers_receipt_write_before_state_publication(
    tmp_path, monkeypatch
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    original_persist_state = ResearchProject.persist_state
    interrupted = False

    def interrupt_completed_state(self, state):
        nonlocal interrupted
        publishes_result = preparation.result_path in state.artifacts
        publishes_receipt = any(
            path.endswith(".registration.json") for path in state.artifacts
        )
        if publishes_result and publishes_receipt and not interrupted:
            interrupted = True
            raise RuntimeError("completed state interrupted")
        return original_persist_state(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", interrupt_completed_state)
    with pytest.raises(RuntimeError, match="completed state interrupted"):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )
    monkeypatch.setattr(ResearchProject, "persist_state", original_persist_state)
    pending = ResearchProject.open(project.root)
    assert preparation.result_path not in pending.state.artifacts
    assert len(
        tuple(
            (project.root / preparation.intent_path).parent.glob(
                "run-*.registration.json"
            )
        )
    ) == 1

    recovered = register_refinement_result(
        pending, candidate.candidate_id, preparation.result_path
    )

    assert recovered.run_id == "run-001"
    assert recovered.next_action == "register_refinement_assessment"
    assert preparation.result_path in ResearchProject.open(project.root).state.artifacts


@pytest.mark.parametrize(
    ("maximum_runs", "maximum_wall_seconds", "error"),
    [
        (1, 120, "refinement_run_budget_exhausted"),
        (2, 60, "refinement_run_wall_time_exhausted"),
    ],
)
def test_prepare_refinement_run_rejects_exhausted_reserved_envelope_stably(
    tmp_path, monkeypatch, maximum_runs, maximum_wall_seconds, error
):
    project, candidate = self_tested_candidate_project_with_envelope(
        tmp_path / "project",
        maximum_runs=maximum_runs,
        maximum_wall_seconds=maximum_wall_seconds,
    )
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    contract = json.loads((project.root / preparation.contract_path).read_bytes())
    write_refinement_result(
        project,
        preparation,
        elapsed_seconds=float(
            contract["envelope"]["reserved_maximum_seconds"]
            if maximum_runs == 2
            else 1
        ),
    )
    register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    if maximum_runs == 2:
        session = json.loads(
            (project.root / "refinement/session.json").read_text(encoding="utf-8")
        )
        created_at = refinement_execution.datetime.fromisoformat(
            session["created_at"]
        )
        monkeypatch.setattr(
            refinement_execution,
            "_utc_now",
            lambda: created_at
            + refinement_execution.timedelta(seconds=maximum_wall_seconds + 1),
        )

    with pytest.raises(ValueError, match=f"^{error}$"):
        prepare_refinement_run(
            ResearchProject.open(project.root), candidate.candidate_id
        )

    assert len(
        tuple((project.root / REFINEMENT_RUN_REGISTRATION_ROOT).glob("*/run-*.intent.json"))
    ) == 2  # reservation intent plus result-registration intent
    assert not tuple(
        (project.root / REFINEMENT_RUN_REGISTRATION_ROOT).glob("*/run-002.*")
    )


@pytest.mark.parametrize("target_kind", ["candidate", "input", "contract"])
def test_register_refinement_result_rejects_bound_identity_drift(
    tmp_path, target_kind
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    if target_kind == "candidate":
        target = project.root / candidate.files[0].path
    elif target_kind == "input":
        target = project.root / "data/input.csv"
    else:
        target = project.root / preparation.contract_path
    original = target.read_bytes()
    target.unlink()
    target.write_bytes(original)

    with pytest.raises(ValueError):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )

    assert not (project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).exists()


def test_register_refinement_result_rejects_environment_drift(tmp_path, monkeypatch):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    original = refinement_execution._inspect_bound_environment

    def changed_environment(package):
        environment, launcher_identity = original(package)
        return replace(environment, fingerprint="0" * 64), launcher_identity

    monkeypatch.setattr(
        refinement_execution, "_inspect_bound_environment", changed_environment
    )

    with pytest.raises(ValueError):
        register_refinement_result(
            project, candidate.candidate_id, preparation.result_path
        )

    assert not (project.root / REFINEMENT_EVIDENCE_MANIFEST_ROOT).exists()


@pytest.mark.parametrize("target_kind", ["result", "manifest", "object"])
def test_registered_refinement_result_rejects_exact_byte_evidence_replacement(
    tmp_path, target_kind
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation)
    registered = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    if target_kind == "result":
        target = project.root / preparation.result_path
    elif target_kind == "manifest":
        target = project.root / registered.evidence_manifest_path
    else:
        manifest = json.loads(
            (project.root / registered.evidence_manifest_path).read_bytes()
        )
        result_object = next(
            item for item in manifest["objects"] if item["role"] == "result"
        )
        target = project.root / result_object["object_path"]
    original = target.read_bytes()
    target.unlink()
    target.write_bytes(original)

    with pytest.raises(ValueError):
        load_refinement_session(ResearchProject.open(project.root))


def _publish_test_artifact(project, path, payload=b"{}\n"):
    target = project.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    reference = refinement_execution.ArtifactRef(
        path, hashlib.sha256(payload).hexdigest(), len(payload)
    )
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={**writable.state.artifacts, path: reference},
        )
    )
    return reference


def _rewrite_report(project, report_path, mutation):
    target = project.root / report_path
    report = json.loads(target.read_text(encoding="utf-8"))
    mutation(report)
    target.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _current_reference(project, path):
    payload = (project.root / path).read_bytes()
    return refinement_execution.ArtifactRef(
        path, hashlib.sha256(payload).hexdigest(), len(payload)
    )


def _assert_no_refinement_run_side_effects(
    project, *, baseline_before, result_before, runs_used_before
):
    reopened = ResearchProject.open(project.root)
    session = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )
    paths = {
        path.relative_to(project.root).as_posix()
        for path in project.root.rglob("*")
        if path.is_file()
    }
    assert session["runs_used"] == runs_used_before
    assert not any("reservation" in path for path in paths)
    assert not any("refinement-manifests" in path for path in paths)
    assert immutable_stage_twelve_snapshot(reopened) == baseline_before
    assert (project.root / "experiment/results.json").read_bytes() == result_before


def test_candidate_self_test_uses_verified_absolute_launcher_and_candidate_cwd(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")

    status = prepare_refinement_self_test(project, candidate.candidate_id)

    assert Path(status.argv[0]).is_absolute()
    assert status.cwd == str(
        project.root.resolve() / "refinement" / "candidates" / candidate.candidate_id
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
    assert context["preparation_intent"]["path"] == status.intent_path
    assert context["intent_id"] == status.intent_id
    assert context["context_id"] == status.context_id
    assert context["context_sha256"] == status.context_sha256
    assert "created_at" not in context
    assert "report_created_at" not in context
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
    assert registration["candidate_manifest"]["sha256"] == (candidate.manifest_sha256)
    assert registration["council_decision"]["sha256"] == candidate.decision_sha256
    assert (
        registration["evidence_packet"]["sha256"]
        == session_before["evidence_packet"]["sha256"]
    )
    assert registration["package_contract"]["sha256"] == (
        candidate.package_contract_sha256
    )
    assert registration["self_test_report"]["path"] == preparation.report_path
    assert registration["preparation_intent"]["path"] == preparation.intent_path
    assert registration["intent_id"] == preparation.intent_id
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
    assert report["report_created_at"] == report["created_at"]
    assert registration["preparation_created_at"].endswith("+00:00")
    assert registration["report_created_at"] == report["created_at"]
    assert registration["preparation_created_at"] != report["created_at"]
    assert "created_at" not in registration
    assert (
        json.loads(
            (project.root / "refinement/session.json").read_text(encoding="utf-8")
        )["runs_used"]
        == session_before["runs_used"]
        == 0
    )
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
    assert (
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        ).next_action
        == "prepare_refinement_run"
    )


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


@pytest.mark.parametrize("artifact", ["intent", "preparation", "report", "receipt"])
def test_registered_candidate_rejects_same_byte_artifact_replacement(
    tmp_path, artifact
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    reopened = ResearchProject.open(project.root)
    if artifact == "intent":
        target = project.root / preparation.intent_path
    elif artifact == "preparation":
        target = project.root / preparation.preparation_path
    elif artifact == "report":
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
def test_registered_candidate_reconstructs_receipt_semantics(tmp_path, loader):
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
    candidate_root = project.root / "refinement" / "candidates" / candidate.candidate_id

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
    assert (
        json.loads(
            (project.root / "refinement/session.json").read_text(encoding="utf-8")
        )["runs_used"]
        == 0
    )
    assert prepared_state.next_action == state_before.next_action


def test_candidate_self_test_registration_rejects_deleted_preparation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    (project.root / preparation.preparation_path).unlink()

    with pytest.raises(ValueError, match="refinement_self_test_preparation_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )


def test_candidate_self_test_report_cannot_replay_from_recreated_preparation(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    first = run_candidate_self_test(project, candidate.candidate_id)
    report_path = project.root / first.report_path
    first_report = report_path.read_bytes()
    report_path.unlink()
    (project.root / first.preparation_path).unlink()
    inode_blocker = (project.root / first.preparation_path).with_name(".inode-blocker")
    inode_blocker.write_bytes(b"occupied\n")
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
    inode_blocker.unlink()
    report_path.write_bytes(first_report)

    assert second.intent_id == first.intent_id
    assert second.context_sha256 != first.context_sha256
    with pytest.raises(ValueError, match="refinement_self_test_report_invalid"):
        register_refinement_self_test(
            project, candidate.candidate_id, second.report_path
        )


@pytest.mark.parametrize(
    "timestamp_mutation",
    [
        {"created_at": "2026-09-02T00:00:00+09:00"},
        {"report_created_at": "2026-09-02T00:00:00+00:00"},
        {"preparation_created_at": "2026-09-02T00:00:00+00:00"},
    ],
    ids=[
        "non-utc-report-created-at",
        "mutated-report-created-at-binding",
        "mutated-preparation-created-at-binding",
    ],
)
def test_candidate_self_test_registration_rejects_report_timestamp_mutation(
    tmp_path, timestamp_mutation
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    report_path = project.root / preparation.report_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update(timestamp_mutation)
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


def test_self_test_preparation_fsyncs_new_directories_before_leaf(
    tmp_path, monkeypatch
):
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


@pytest.mark.parametrize("operation", ["prepare", "register"])
@pytest.mark.parametrize("session_attack", ["parent", "absolute"])
def test_self_test_session_component_race_cannot_escape_or_publish_state(
    tmp_path, monkeypatch, operation, session_attack
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    if operation == "register":
        preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    session_path = project.root / "refinement/session.json"
    original_session_bytes = session_path.read_bytes()
    session_payload = json.loads(original_session_bytes)
    if session_attack == "parent":
        malicious_session = "../escaped-self-test-session"
        escaped = project.root / ".researchclaw/escaped-self-test-session"
    else:
        escaped = tmp_path / "absolute-self-test-session"
        malicious_session = str(escaped)
    malicious_payload = {**session_payload, "session_id": malicious_session}
    original_read = getattr(refinement_execution, "_read_bounded_json", None)
    original_hold = refinement_execution._hold_candidate_context
    race_injected = False

    def change_restore_session():
        nonlocal race_injected
        session_path.write_text(
            json.dumps(malicious_payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        session_path.write_bytes(original_session_bytes)
        race_injected = True

    def race_unbound_session_read(path, *args, **kwargs):
        nonlocal race_injected
        assert original_read is not None
        if Path(path) == session_path and not race_injected:
            session_path.write_text(
                json.dumps(malicious_payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            try:
                value = original_read(path, *args, **kwargs)
            finally:
                session_path.write_bytes(original_session_bytes)
            race_injected = True
            return value
        return original_read(path, *args, **kwargs)

    def race_after_held_context(*args, **kwargs):
        held = original_hold(*args, **kwargs)
        if not race_injected:
            change_restore_session()
        return held

    if original_read is not None:
        monkeypatch.setattr(
            refinement_execution, "_read_bounded_json", race_unbound_session_read
        )
    monkeypatch.setattr(
        refinement_execution, "_hold_candidate_context", race_after_held_context
    )

    with pytest.raises(ValueError):
        if operation == "prepare":
            prepare_refinement_self_test(project, candidate.candidate_id)
        else:
            register_refinement_self_test(
                project, candidate.candidate_id, preparation.report_path
            )

    assert race_injected
    assert not escaped.exists()
    assert ResearchProject.open(project.root).state == state_before


@pytest.mark.parametrize(
    "session_id,candidate_id",
    [
        ("../escaped", "candidate-001"),
        ("0" * 32, "../candidate-001"),
        ("A" * 32, "candidate-001"),
    ],
)
def test_anchored_record_rejects_unsafe_components_before_filesystem_access(
    tmp_path, monkeypatch, session_id, candidate_id
):
    project, _candidate = registered_candidate_project(tmp_path / "project")
    calls = 0
    original_open = refinement_execution.os.open

    def count_open(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_open(*args, **kwargs)

    monkeypatch.setattr(refinement_execution.os, "open", count_open)

    with pytest.raises(
        ValueError, match="refinement_self_test_registration_recovery_invalid"
    ):
        refinement_execution._write_anchored_record(
            project,
            session_id=session_id,
            candidate_id=candidate_id,
            leaf_name="candidate-001.preparation.json",
            payload_builder=lambda _identity: {"schema_version": 1},
            error_code="refinement_self_test_registration_recovery_invalid",
        )

    assert calls == 0


@pytest.mark.parametrize("kind", ["report", "preparation", "intent"])
def test_refinement_state_rejects_unknown_candidate_self_test_artifact(tmp_path, kind):
    project, _candidate = registered_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    if kind == "report":
        path = (
            "refinement/candidates/candidate-999/"
            "package_metadata/self_test_report.json"
        )
    elif kind == "preparation":
        path = (
            f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
            "candidate-999.preparation.json"
        )
    else:
        path = (
            f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
            "candidate-999.preparation.intent.json"
        )
    _publish_test_artifact(project, path)

    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        load_refinement_session(ResearchProject.open(project.root))


def test_refinement_state_rejects_unclassified_self_test_namespace_artifact(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    session_id = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["session_id"]
    path = (
        f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/"
        f"{candidate.candidate_id}.unexpected.json"
    )
    _publish_test_artifact(project, path)

    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        load_refinement_session(ResearchProject.open(project.root))


def test_refinement_state_reconstructs_registered_preparation_semantics(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_self_test(project, candidate.candidate_id)
    target = project.root / preparation.preparation_path
    forged = json.loads(target.read_text(encoding="utf-8"))
    forged["producer"] = "reviewer-agent"
    forged_bytes = json.dumps(
        forged, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    target.write_bytes(forged_bytes)
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={
                **writable.state.artifacts,
                preparation.preparation_path: refinement_execution.ArtifactRef(
                    preparation.preparation_path,
                    hashlib.sha256(forged_bytes).hexdigest(),
                    len(forged_bytes),
                ),
            },
        )
    )

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        load_refinement_session(ResearchProject.open(project.root))


def test_registered_self_test_with_stale_marker_fails_closed(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(writable.state, next_action="prepare_refinement_self_test")
    )

    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        load_refinement_session(ResearchProject.open(project.root))


@pytest.mark.parametrize("alter_orphan", [False, True])
def test_candidate_self_test_preparation_crash_recovers_only_exact_orphan(
    tmp_path, monkeypatch, alter_orphan
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    state_before = ResearchProject.open(project.root).state
    baseline_before = immutable_stage_twelve_snapshot(project)
    result_before = (project.root / "experiment/results.json").read_bytes()
    runs_used_before = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["runs_used"]

    def interrupt_after_preparation_write():
        raise RuntimeError("preparation interrupted")

    monkeypatch.setattr(
        refinement_execution,
        "_after_anchored_preparation_write",
        interrupt_after_preparation_write,
        raising=False,
    )
    with pytest.raises(RuntimeError, match="preparation interrupted"):
        prepare_refinement_self_test(project, candidate.candidate_id)

    pending_state = ResearchProject.open(project.root).state
    assert pending_state != state_before
    intent_paths = [
        path
        for path in pending_state.artifacts
        if path.endswith(f"/{candidate.candidate_id}.preparation.intent.json")
    ]
    assert len(intent_paths) == 1
    assert not any(
        path.endswith(f"/{candidate.candidate_id}.preparation.json")
        for path in pending_state.artifacts
    )
    assert (
        load_refinement_session(ResearchProject.open(project.root)).next_action
        == "prepare_refinement_self_test"
    )
    orphan = next(
        (project.root / REFINEMENT_SELF_TEST_REGISTRATION_ROOT).glob(
            f"*/{candidate.candidate_id}.preparation.json"
        )
    )
    orphan_bytes = orphan.read_bytes()
    orphan_identity = (orphan.stat().st_dev, orphan.stat().st_ino)
    if alter_orphan:
        forged = json.loads(orphan_bytes)
        forged["created_at"] = "2026-09-02T00:00:00+00:00"
        context = {
            key: value
            for key, value in forged.items()
            if key not in {"context_id", "context_sha256"}
        }
        forged_digest = hashlib.sha256(_canonical_bytes(context)).hexdigest()
        forged["context_id"] = f"refinement-self-test-{forged_digest[:32]}"
        forged["context_sha256"] = forged_digest
        orphan.write_bytes(_canonical_bytes(forged))
    monkeypatch.setattr(
        refinement_execution,
        "_after_anchored_preparation_write",
        lambda: None,
        raising=False,
    )

    if alter_orphan:
        with pytest.raises(
            ValueError, match="refinement_self_test_preparation_invalid"
        ):
            prepare_refinement_self_test(project, candidate.candidate_id)
        assert ResearchProject.open(project.root).state == pending_state
    else:
        status = prepare_refinement_self_test(project, candidate.candidate_id)
        assert (orphan.stat().st_dev, orphan.stat().st_ino) == orphan_identity
        assert orphan.read_bytes() == orphan_bytes
        assert ResearchProject.open(project.root).state.artifacts[
            status.preparation_path
        ] == refinement_execution.ArtifactRef(
            status.preparation_path,
            hashlib.sha256(orphan_bytes).hexdigest(),
            len(orphan_bytes),
        )
    _assert_no_refinement_run_side_effects(
        project,
        baseline_before=baseline_before,
        result_before=result_before,
        runs_used_before=runs_used_before,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update(metrics=[]),
        lambda report: report["metrics"].append(
            {"name": "extra", "actual": 0.0, "expected": 0.0, "tolerance": 0.0}
        ),
        lambda report: report["metrics"][0].update(actual=float("nan")),
        lambda report: report["metrics"][0].update(actual="0.5"),
        lambda report: report["metrics"][0].update(actual=0.6),
        lambda report: report["metrics"][0].update(expected=0.6),
        lambda report: report["metrics"][0].update(tolerance=0.1),
    ],
    ids=[
        "missing-metric",
        "extra-metric",
        "nonfinite-actual",
        "wrong-type-actual",
        "out-of-tolerance-actual",
        "mutated-expected",
        "mutated-tolerance",
    ],
)
def test_candidate_self_test_report_rejects_invalid_metrics_without_publication(
    tmp_path, mutation
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    _rewrite_report(project, preparation.report_path, mutation)

    with pytest.raises(ValueError, match="^refinement_self_test_report_invalid$"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )

    assert ResearchProject.open(project.root).state == state_before


def test_candidate_self_test_publishes_intent_before_preparation_and_resumes(
    tmp_path, monkeypatch
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    result_before = (project.root / "experiment/results.json").read_bytes()
    runs_used_before = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["runs_used"]
    observed: dict[str, object] = {}

    def interrupt_after_intent_publication():
        pending = ResearchProject.open(project.root).state
        intent_paths = [
            path
            for path in pending.artifacts
            if path.endswith(f"/{candidate.candidate_id}.preparation.intent.json")
        ]
        assert len(intent_paths) == 1
        intent_path = intent_paths[0]
        intent_bytes = (project.root / intent_path).read_bytes()
        assert pending.artifacts[intent_path] == refinement_execution.ArtifactRef(
            intent_path, hashlib.sha256(intent_bytes).hexdigest(), len(intent_bytes)
        )
        assert not tuple(
            (project.root / REFINEMENT_SELF_TEST_REGISTRATION_ROOT).glob(
                f"*/{candidate.candidate_id}.preparation.json"
            )
        )
        observed.update(path=intent_path, payload=intent_bytes, state=pending)
        raise RuntimeError("intent published")

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_self_test_intent_publication",
        interrupt_after_intent_publication,
        raising=False,
    )
    with pytest.raises(RuntimeError, match="intent published"):
        prepare_refinement_self_test(project, candidate.candidate_id)

    assert ResearchProject.open(project.root).state == observed["state"]
    assert (
        load_refinement_session(ResearchProject.open(project.root)).next_action
        == "prepare_refinement_self_test"
    )
    _assert_no_refinement_run_side_effects(
        project,
        baseline_before=baseline_before,
        result_before=result_before,
        runs_used_before=runs_used_before,
    )

    monkeypatch.setattr(
        refinement_execution,
        "_after_refinement_self_test_intent_publication",
        lambda: None,
        raising=False,
    )
    resumed = prepare_refinement_self_test(
        ResearchProject.open(project.root), candidate.candidate_id
    )

    assert resumed.intent_path == observed["path"]
    assert (project.root / resumed.intent_path).read_bytes() == observed["payload"]
    assert (project.root / resumed.preparation_path).is_file()
    assert ResearchProject.open(project.root).state.artifacts[resumed.intent_path] == (
        _current_reference(project, resumed.intent_path)
    )
    _assert_no_refinement_run_side_effects(
        project,
        baseline_before=baseline_before,
        result_before=result_before,
        runs_used_before=runs_used_before,
    )


def test_refinement_state_rejects_preparation_without_intent(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_self_test(project, candidate.candidate_id)
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={
                path: reference
                for path, reference in writable.state.artifacts.items()
                if path != preparation.intent_path
            },
        )
    )

    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        load_refinement_session(ResearchProject.open(project.root))


def test_candidate_self_test_report_cannot_replay_across_intents(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    first = run_candidate_self_test(project, candidate.candidate_id)
    first_context = json.loads(first.argv[-1])
    old_report = (project.root / first.report_path).read_bytes()
    old_intent_id = first_context["intent_id"]
    assert first_context["preparation_intent"]["path"] == first.intent_path
    (project.root / first.report_path).unlink()
    (project.root / first.preparation_path).unlink()
    (project.root / first.intent_path).unlink()
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={
                path: reference
                for path, reference in writable.state.artifacts.items()
                if path not in {first.preparation_path, first.intent_path}
            },
        )
    )

    second = prepare_refinement_self_test(
        ResearchProject.open(project.root), candidate.candidate_id
    )
    second_context = json.loads(second.argv[-1])
    assert second_context["intent_id"] != old_intent_id
    (project.root / second.report_path).write_bytes(old_report)

    with pytest.raises(ValueError, match="^refinement_self_test_report_invalid$"):
        register_refinement_self_test(
            project, candidate.candidate_id, second.report_path
        )


def test_registered_self_test_rejects_coherent_timestamp_rewrite_without_intent(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    register_refinement_self_test(
        project, candidate.candidate_id, preparation.report_path
    )
    state = ResearchProject.open(project.root).state
    intent_path = preparation.intent_path
    intent_reference = state.artifacts[intent_path]
    registration_path = next(
        path
        for path in state.artifacts
        if path.startswith(f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/")
        and path.endswith(f"/{candidate.candidate_id}.json")
    )
    rewritten_at = "2026-09-02T00:00:00+00:00"

    preparation_target = project.root / preparation.preparation_path
    preparation_payload = json.loads(preparation_target.read_bytes())
    preparation_payload["created_at"] = rewritten_at
    preparation_base = {
        key: value
        for key, value in preparation_payload.items()
        if key not in {"context_id", "context_sha256"}
    }
    context_digest = hashlib.sha256(_canonical_bytes(preparation_base)).hexdigest()
    preparation_payload["context_id"] = (
        f"refinement-self-test-{context_digest[:32]}"
    )
    preparation_payload["context_sha256"] = context_digest
    preparation_target.write_bytes(_canonical_bytes(preparation_payload))
    preparation_reference = _current_reference(project, preparation.preparation_path)

    report_target = project.root / preparation.report_path
    report_payload = json.loads(report_target.read_bytes())
    report_payload.update(
        {
            "created_at": rewritten_at,
            "report_created_at": rewritten_at,
            "preparation_created_at": rewritten_at,
            "preparation": {
                "path": preparation_reference.path,
                "sha256": preparation_reference.sha256,
                "size": preparation_reference.size,
            },
            "context_id": preparation_payload["context_id"],
            "context_sha256": preparation_payload["context_sha256"],
        }
    )
    report_target.write_bytes(_canonical_bytes(report_payload))
    report_reference = _current_reference(project, preparation.report_path)
    report_stat = report_target.stat()

    receipt_target = project.root / registration_path
    receipt_payload = json.loads(receipt_target.read_bytes())
    receipt_payload.update(
        {
            "preparation_created_at": rewritten_at,
            "report_created_at": rewritten_at,
            "preparation": {
                "path": preparation_reference.path,
                "sha256": preparation_reference.sha256,
                "size": preparation_reference.size,
            },
            "context_id": preparation_payload["context_id"],
            "context_sha256": preparation_payload["context_sha256"],
            "self_test_report": {
                "path": report_reference.path,
                "sha256": report_reference.sha256,
                "size": report_reference.size,
            },
            "report_filesystem_identity": {
                "device": report_stat.st_dev,
                "inode": report_stat.st_ino,
                "mode": report_stat.st_mode,
                "links": report_stat.st_nlink,
                "size": report_stat.st_size,
                "mtime_ns": report_stat.st_mtime_ns,
                "ctime_ns": report_stat.st_ctime_ns,
            },
        }
    )
    for artifact in receipt_payload["artifacts"]:
        if artifact["path"] == preparation.preparation_path:
            artifact.update(
                sha256=preparation_reference.sha256, size=preparation_reference.size
            )
        elif artifact["path"] == preparation.report_path:
            artifact.update(sha256=report_reference.sha256, size=report_reference.size)
    receipt_target.write_bytes(_canonical_bytes(receipt_payload))
    registration_reference = _current_reference(project, registration_path)
    writable = ResearchProject.open(project.root)
    writable.persist_state(
        replace(
            writable.state,
            artifacts={
                **writable.state.artifacts,
                preparation.preparation_path: preparation_reference,
                preparation.report_path: report_reference,
                registration_path: registration_reference,
            },
        )
    )

    assert ResearchProject.open(project.root).state.artifacts[intent_path] == (
        intent_reference
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        load_refinement_session(ResearchProject.open(project.root))


def test_candidate_self_test_huge_integer_metric_has_stable_error_and_no_side_effects(
    tmp_path,
):
    project, candidate = registered_candidate_project(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    result_before = (project.root / "experiment/results.json").read_bytes()
    runs_used_before = json.loads(
        (project.root / "refinement/session.json").read_text(encoding="utf-8")
    )["runs_used"]
    preparation = run_candidate_self_test(project, candidate.candidate_id)
    state_before = ResearchProject.open(project.root).state
    _rewrite_report(
        project,
        preparation.report_path,
        lambda report: report["metrics"][0].update(actual=10**1000),
    )

    with pytest.raises(ValueError, match="^refinement_self_test_report_invalid$"):
        register_refinement_self_test(
            project, candidate.candidate_id, preparation.report_path
        )

    assert ResearchProject.open(project.root).state == state_before
    _assert_no_refinement_run_side_effects(
        project,
        baseline_before=baseline_before,
        result_before=result_before,
        runs_used_before=runs_used_before,
    )
