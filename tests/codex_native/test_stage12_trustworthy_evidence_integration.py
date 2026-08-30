import hashlib
import json
import os
from pathlib import Path
import subprocess
import tracemalloc

import pytest

import researchclaw.core.evidence_registration as registration
import researchclaw.core.evidence_store as evidence_store
import researchclaw.core.research_execution as research_execution
from researchclaw.codex.cli import main as cli_main
from researchclaw.core.evidence_store import EvidenceSource, EvidenceStore
from researchclaw.core.events import EventLog
from researchclaw.core.handoff import build_handoff
from researchclaw.core.project import ResearchProject
from researchclaw.core.research_execution import (
    prepare_research_execution,
    register_research_result,
)
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    build_stage_twelve_project,
)


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _run_exact_known_answer(project: ResearchProject):
    status = prepare_research_execution(project)
    assert Path(status.argv[0]).is_absolute()
    before = _hash_tree(project.root)
    completed = subprocess.run(
        status.argv,
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    after = _hash_tree(project.root)
    assert {
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    } == {"experiment/results.json"}
    result = json.loads(
        (project.root / "experiment/results.json").read_text(encoding="utf-8")
    )
    assert result["metrics"]["primary"]["value"] == 0.5
    return status, before, after


def test_exact_argv_registration_is_immutable_and_filesystem_scoped(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status, _, execution_tree = _run_exact_known_answer(project)
    registered = register_research_result(project, "experiment/results.json")
    registration_tree = _hash_tree(project.root)
    changed = {
        path
        for path in execution_tree.keys() | registration_tree.keys()
        if execution_tree.get(path) != registration_tree.get(path)
    }
    assert changed
    assert all(
        path == "evaluation/events.jsonl"
        or path.startswith(".researchclaw/")
        for path in changed
    )
    manifest = registration.load_evidence_manifest(
        project.root, registered.manifest_path
    )
    result_object = next(item for item in manifest["objects"] if item["role"] == "result")
    immutable_result = project.root / result_object["object_path"]
    immutable_bytes = immutable_result.read_bytes()
    assert hashlib.sha256(immutable_bytes).hexdigest() == result_object["sha256"]
    assert tuple(status.argv) == status.argv

    (project.root / "data/input.csv").write_bytes(b"mutable input removed from trust\n")
    (project.root / "experiment/results.json").unlink()
    assert json.loads(immutable_bytes)["metrics"]["primary"]["value"] == 0.5
    assert build_handoff(ResearchProject.open(project.root)).current_stage == 13


@pytest.mark.parametrize(
    "relative_path",
    (
        "data/input.csv",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/package_contract.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    ),
)
def test_post_validation_source_mutation_never_reaches_stage_thirteen(
    tmp_path, monkeypatch, relative_path
):
    project = build_approved_stage_twelve_project(tmp_path / relative_path.replace("/", "-"))
    _run_exact_known_answer(project)
    target = project.root / relative_path

    def mutate_after_validation(_validated):
        target.write_bytes(target.read_bytes() + b"\npost-validation mutation\n")

    monkeypatch.setattr(registration, "_after_strict_validation", mutate_after_validation)
    with pytest.raises(ValueError, match="research_result_file_invalid"):
        register_research_result(project, "experiment/results.json")
    reopened = ResearchProject.open_readonly(project.root)
    assert reopened.state.current_stage == 12
    assert not list((project.root / ".researchclaw/evidence/manifests").glob("*.json"))


@pytest.mark.parametrize(
    "relative_path",
    (
        "data/input.csv",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/package_contract.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    ),
)
def test_source_mutation_during_validation_never_reaches_stage_thirteen(
    tmp_path, monkeypatch, relative_path
):
    project = build_approved_stage_twelve_project(
        tmp_path / ("validation-" + relative_path.replace("/", "-"))
    )
    _run_exact_known_answer(project)
    source = project.root / relative_path

    def mutate_during_validation():
        source.write_bytes(source.read_bytes() + b"\nforeign-during-validation\n")

    monkeypatch.setattr(
        research_execution,
        "_after_research_result_snapshot",
        mutate_during_validation,
    )
    with pytest.raises(ValueError):
        register_research_result(project, "experiment/results.json")
    assert ResearchProject.open_readonly(project.root).state.current_stage == 12
    assert not list((project.root / ".researchclaw/evidence/manifests").glob("*.json"))


@pytest.mark.parametrize(
    "hook_name",
    ("_after_manifest_published", "_after_state_saved"),
)
def test_mutable_drift_after_immutable_boundary_recovers_only_bound_bytes(
    tmp_path, monkeypatch, hook_name
):
    project = build_approved_stage_twelve_project(tmp_path / hook_name)
    _run_exact_known_answer(project)
    result_path = project.root / "experiment/results.json"

    def mutate_and_interrupt(*_args):
        result_path.write_bytes(b'{"foreign":"mutable"}\n')
        (project.root / "data/input.csv").write_bytes(b"foreign mutable input\n")
        (project.root / "experiment/code/main.py").write_bytes(b"foreign code\n")
        (project.root / "experiment/code/config.json").write_bytes(b"{}\n")
        (project.root / "experiment/package_contract.json").write_bytes(b"{}\n")
        (project.root / "experiment/execution_contract.json").write_bytes(b"{}\n")
        raise OSError("durability seam")

    monkeypatch.setattr(registration, hook_name, mutate_and_interrupt)
    with pytest.raises(OSError, match="durability seam"):
        register_research_result(project, "experiment/results.json")
    monkeypatch.undo()
    handoff = build_handoff(ResearchProject.open(project.root))
    assert handoff.current_stage == 13
    current = ResearchProject.open_readonly(project.root)
    manifest_path = next(
        path
        for path in current.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    )
    manifest = registration.load_evidence_manifest(project.root, manifest_path)
    result_object = next(item for item in manifest["objects"] if item["role"] == "result")
    payload = json.loads((project.root / result_object["object_path"]).read_bytes())
    assert payload["metrics"]["primary"]["value"] == 0.5


def test_registration_event_path_is_streaming_and_does_not_call_read_all(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    _run_exact_known_answer(project)

    def forbidden_read_all(_self):
        raise AssertionError("registration event helper must stream by reserved offset")

    monkeypatch.setattr(EventLog, "read_all", forbidden_read_all)
    assert register_research_result(project, "experiment/results.json").current_stage == 13


@pytest.mark.parametrize(
    "relative_path",
    (
        "data/input.csv",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/package_contract.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    ),
)
def test_source_mutation_before_validation_fails_closed_at_stage_twelve(
    tmp_path, relative_path
):
    project = build_approved_stage_twelve_project(
        tmp_path / ("before-" + relative_path.replace("/", "-"))
    )
    _run_exact_known_answer(project)
    source = project.root / relative_path
    source.write_bytes(source.read_bytes() + b"\nforeign-before-validation\n")
    with pytest.raises(ValueError):
        register_research_result(project, "experiment/results.json")
    assert ResearchProject.open_readonly(project.root).state.current_stage == 12


@pytest.mark.parametrize(
    "relative_path",
    (
        "data/input.csv",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/package_contract.json",
        "experiment/execution_contract.json",
        "experiment/results.json",
    ),
)
def test_source_mutation_during_object_copy_never_publishes_mismatched_bytes(
    tmp_path, monkeypatch, relative_path
):
    project = build_approved_stage_twelve_project(
        tmp_path / ("during-" + relative_path.replace("/", "-"))
    )
    _run_exact_known_answer(project)
    source = project.root / relative_path
    identity = (source.stat().st_dev, source.stat().st_ino)
    original = source.read_bytes()
    mutated = False

    def mutate_during_copy(descriptor):
        nonlocal mutated
        current = os.fstat(descriptor)
        if not mutated and (current.st_dev, current.st_ino) == identity:
            mutated = True
            source.write_bytes(original + b"\nforeign-during-copy\n")

    monkeypatch.setattr(evidence_store, "_before_source_recheck", mutate_during_copy)
    with pytest.raises(ValueError, match="research_result_file_invalid"):
        register_research_result(project, "experiment/results.json")
    assert ResearchProject.open_readonly(project.root).state.current_stage == 12
    manifests = project.root / ".researchclaw/evidence/manifests"
    assert not list(manifests.glob("*.json"))


def _read_cli_json(capsys, argv: list[str]) -> dict[str, object]:
    assert cli_main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_complete_public_recovery_chain_and_repeated_execution_is_reproducible(
    tmp_path, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "public-chain", register_self_test=False
    )
    root = str(project.root)
    self_test = _read_cli_json(
        capsys, ["experiment", "prepare-self-test", root, "--json"]
    )
    assert Path(self_test["argv"][0]).is_absolute()
    completed = subprocess.run(
        self_test["argv"], cwd=project.root, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    _read_cli_json(capsys, self_test["registration_argv"][1:])
    _read_cli_json(
        capsys,
        ["approve", root, "--decision", "approve", "--note", "release matrix", "--json"],
    )
    first_preparation = _read_cli_json(
        capsys, ["execution", "prepare-run", root, "--json"]
    )
    first_run = subprocess.run(
        first_preparation["argv"],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first_run.returncode == 0, first_run.stderr
    first_bytes = (project.root / "experiment/results.json").read_bytes()
    first_payload = json.loads(first_bytes)
    assert first_payload["metrics"]["primary"]["value"] == 0.5

    _read_cli_json(
        capsys,
        [
            "execution", "quarantine-result", root, "--reason", "repeat_probe",
            "--confirm", "--json",
        ],
    )
    _read_cli_json(
        capsys,
        ["execution", "cleanup-quarantined-result", root, "--confirm", "--json"],
    )
    second_preparation = _read_cli_json(
        capsys, ["execution", "prepare-run", root, "--json"]
    )
    assert second_preparation["argv"] == first_preparation["argv"]
    second_run = subprocess.run(
        second_preparation["argv"],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert second_run.returncode == 0, second_run.stderr
    second_bytes = (project.root / "experiment/results.json").read_bytes()
    assert second_bytes == first_bytes
    registered = _read_cli_json(
        capsys,
        [
            "execution", "register-result", root, "--result",
            "experiment/results.json", "--confirm-research-result", "--json",
        ],
    )
    assert registered["current_stage"] == 13
    result_sha256 = hashlib.sha256(first_bytes).hexdigest()
    assert (project.root / f".researchclaw/evidence/objects/{result_sha256}").is_file()


def test_stale_contract_public_route_reprepares_without_stage_regression(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "stale-contract")
    root = str(project.root)
    preparation = _read_cli_json(
        capsys, ["execution", "prepare-run", root, "--json"]
    )
    completed = subprocess.run(
        preparation["argv"],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    contract = project.root / "experiment/execution_contract.json"
    contract.write_bytes(b"{}")
    status = _read_cli_json(capsys, ["status", root, "--json"])
    assert status["current_stage"] == 12
    assert status["next_action"] == "prepare_run"
    reprepared = _read_cli_json(
        capsys, ["execution", "prepare-run", root, "--json"]
    )
    assert Path(reprepared["argv"][0]).is_absolute()
    assert json.loads(contract.read_bytes())["contract_id"]
    assert cli_main(
        [
            "execution", "register-result", root, "--result",
            "experiment/results.json", "--confirm-research-result", "--json",
        ]
    ) == 2
    capsys.readouterr()
    assert ResearchProject.open_readonly(project.root).state.current_stage == 12


def test_32_mib_evidence_identity_and_copy_stay_below_8_mib_python_peak(tmp_path):
    root = tmp_path / "streaming"
    source_path = root / "data/large.bin"
    source_path.parent.mkdir(parents=True)
    digest = hashlib.sha256()
    chunk = b"stage12-streaming-evidence\n" * 4096
    remaining = 32 * 1024 * 1024
    with source_path.open("wb") as stream:
        while remaining:
            payload = chunk[: min(len(chunk), remaining)]
            stream.write(payload)
            digest.update(payload)
            remaining -= len(payload)
    source = EvidenceSource(
        role="input",
        path="data/large.bin",
        expected_sha256=digest.hexdigest(),
        expected_size=source_path.stat().st_size,
    )
    store = EvidenceStore(root)
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    store.preflight((source,))
    published = store.publish(source)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert published.sha256 == source.expected_sha256
    assert peak - baseline < 8 * 1024 * 1024
