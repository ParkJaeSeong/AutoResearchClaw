"""Tests for the closed execution-environment evidence contract."""

from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv

import pytest

import researchclaw.core.execution_environment as execution_environment
import researchclaw.core.experiment_package_contract as package_contract
import researchclaw.core.research_execution as research_execution
from researchclaw.core.execution_environment import (
    canonical_environment_payload,
    inspect_execution_environment,
    normalize_required_distributions,
)
from researchclaw.core.experiment_package_contract import (
    SELF_TEST_REPORT_PATH,
    validate_experiment_package_contract,
)
from researchclaw.core.research_execution import prepare_research_execution
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    build_known_answer_experiment_package,
)


def _resolved_interpreter() -> Path:
    return Path(sys.executable).resolve(strict=True)


def test_inspection_returns_a_stable_identity_bound_fingerprint():
    environment = inspect_execution_environment(_resolved_interpreter(), ())

    assert environment.interpreter == str(_resolved_interpreter())
    assert environment.fingerprint == inspect_execution_environment(
        _resolved_interpreter(), ()
    ).fingerprint
    assert dict(environment.dependencies) == {}


def test_inspection_rejects_non_absolute_symlink_and_missing_distribution(tmp_path):
    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(Path("python"), ())

    alias = tmp_path / "python-alias"
    alias.symlink_to(_resolved_interpreter())
    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(alias, ())

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(
            _resolved_interpreter(), ("does-not-exist-for-researchclaw",)
        )


def test_required_distribution_names_are_closed_and_canonical():
    assert normalize_required_distributions(("pytest", "py-yaml")) == (
        "py-yaml",
        "pytest",
    )
    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        normalize_required_distributions(("py-yaml", "py_yaml"))


def test_canonical_payload_normalizes_the_generated_collector_text_fields():
    payload = canonical_environment_payload(
        interpreter="/absolute/python",
        interpreter_identity={"sha256": "a" * 64},
        python_implementation="  CPython  ",
        python_version=" 3.11.0 ",
        python_full_version=" Python 3.11.0 ",
        python_build=("main", "  Jan 01  "),
        platform=" DARWIN ",
        machine=" ARM64 ",
        dependencies={"pytest": "8.0"},
    )

    assert payload["python_implementation"] == "cpython"
    assert payload["python_version"] == "3.11.0"
    assert payload["python_full_version"] == "Python 3.11.0"
    assert payload["platform"] == "darwin"
    assert payload["machine"] == "arm64"


def test_generated_self_test_uses_the_canonical_environment_fingerprint(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    contract_path = project.root / "experiment/package_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["dependencies"] = ["pytest"]
    contract_path.write_text(json.dumps(contract, sort_keys=True) + "\n")
    package = validate_experiment_package_contract(project)

    completed = subprocess.run(
        [sys.executable, package.entry_point, *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((project.root / SELF_TEST_REPORT_PATH).read_text())
    environment = inspect_execution_environment(
        _resolved_interpreter(), package.required_distributions
    )
    assert report["environment_fingerprint"] == environment.fingerprint
    assert environment.python_full_version == sys.version.strip()
    assert environment.python_build == tuple(platform.python_build())
    assert dict(environment.dependencies) == {"pytest": environment.dependencies["pytest"]}
    assert "researchclaw" not in (project.root / package.entry_point).read_text()


def test_generated_self_test_matches_a_venv_interpreter_contract(tmp_path):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment_root)
    interpreter = environment_root / "bin/python"
    project = build_known_answer_experiment_package(tmp_path / "project")
    package = validate_experiment_package_contract(project)

    completed = subprocess.run(
        [str(interpreter), package.entry_point, *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((project.root / SELF_TEST_REPORT_PATH).read_text())
    assert report["environment_fingerprint"] == inspect_execution_environment(
        interpreter, package.required_distributions
    ).fingerprint


def test_descriptor_probe_never_reopens_a_replaced_interpreter_path(
    tmp_path, monkeypatch
):
    interpreter = tmp_path / "python"
    replacement = tmp_path / "replacement"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)
    replacement.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    replacement.chmod(0o755)
    replaced = False

    def replace_path(_verified):
        nonlocal replaced
        os.replace(replacement, interpreter)
        replaced = True

    monkeypatch.setattr(execution_environment, "_before_descriptor_probe", replace_path)

    try:
        environment = inspect_execution_environment(interpreter, ())
    except ValueError as error:
        assert str(error) == "execution_environment_unavailable"
    else:
        assert environment.python_implementation == "cpython"
        assert environment.fingerprint
    assert replaced
    assert interpreter.read_text(encoding="utf-8") == "#!/bin/sh\nexit 99\n"


def test_probe_rejects_repointed_current_process_path_without_a_snapshot(
    tmp_path, monkeypatch
):
    interpreter = tmp_path / "not-python"
    interpreter.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    interpreter.chmod(0o755)

    monkeypatch.setattr(sys, "executable", str(interpreter))
    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())


def test_probe_runs_a_verified_snapshot_and_removes_it(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    environment = inspect_execution_environment(interpreter, ())

    assert environment.interpreter == str(interpreter)
    assert environment.python_implementation == "cpython"
    assert not list(tmp_path.glob(".researchclaw-execution-*"))


def test_probe_removes_snapshot_when_snapshot_execution_fails(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)
    attempted: list[list[str]] = []

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    monkeypatch.setattr(
        execution_environment.subprocess,
        "run",
        lambda argv, **_kwargs: (
            attempted.append(argv)
            or subprocess.CompletedProcess(argv, 1, stdout="", stderr="failed")
        ),
    )

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())

    assert attempted and Path(attempted[0][0]).parent == interpreter.parent
    assert not list(tmp_path.glob(".researchclaw-execution-*"))


def test_probe_rechecks_original_descriptor_after_snapshot_runtime(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)
    original_identity = execution_environment._descriptor_identity
    original_run = subprocess.run
    runtime_finished = False

    def run_snapshot(argv, **kwargs):
        nonlocal runtime_finished
        completed = original_run(argv, **kwargs)
        runtime_finished = True
        return completed

    def changed_after_runtime(descriptor):
        identity = original_identity(descriptor)
        if runtime_finished and identity["inode"] == interpreter.stat().st_ino:
            return {**identity, "sha256": "0" * 64}
        return identity

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    monkeypatch.setattr(execution_environment.subprocess, "run", run_snapshot)
    monkeypatch.setattr(execution_environment, "_descriptor_identity", changed_after_runtime)

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())

    assert not list(tmp_path.glob(".researchclaw-execution-*"))


def test_probe_rejects_snapshot_replaced_before_subprocess(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    attacker = tmp_path / "attacker"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)
    attacker.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    attacker.chmod(0o755)

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    monkeypatch.setattr(
        execution_environment,
        "_before_snapshot_subprocess",
        lambda snapshot: os.replace(attacker, snapshot.path),
        raising=False,
    )

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())

    snapshots = list(tmp_path.glob(".researchclaw-execution-*"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "#!/bin/sh\nexit 99\n"


def test_probe_rejects_snapshot_replaced_after_subprocess_starts(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    attacker = tmp_path / "attacker"
    shutil.copy2(_resolved_interpreter(), interpreter)
    interpreter.chmod(0o755)
    attacker.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    attacker.chmod(0o755)
    original_run = subprocess.run

    def run_then_replace(argv, **kwargs):
        completed = original_run(argv, **kwargs)
        os.replace(attacker, Path(argv[0]))
        return completed

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    monkeypatch.setattr(execution_environment.subprocess, "run", run_then_replace)

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())

    snapshots = list(tmp_path.glob(".researchclaw-execution-*"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "#!/bin/sh\nexit 99\n"


def test_snapshot_probe_preserves_venv_distribution_resolution(tmp_path, monkeypatch):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment_root)
    interpreter = environment_root / "bin/python"
    site_packages = next((environment_root / "lib").glob("python*/site-packages"))
    metadata = site_packages / "private_probe-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: private-probe\nVersion: 1.2.3\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        execution_environment,
        "_descriptor_execution_path",
        lambda _descriptor: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )
    environment = inspect_execution_environment(interpreter, ("private-probe",))

    assert environment.interpreter == str(interpreter)
    assert environment.dependencies == {"private-probe": "1.2.3"}


def test_environment_drift_invalidates_the_registered_self_test_and_prepare(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    original = package_contract.inspect_execution_environment

    monkeypatch.setattr(
        package_contract,
        "inspect_execution_environment",
        lambda interpreter, distributions: replace(
            original(interpreter, distributions), fingerprint="f" * 64
        ),
    )
    monkeypatch.setattr(
        research_execution,
        "inspect_execution_environment",
        lambda interpreter, distributions: replace(
            original(interpreter, distributions), fingerprint="f" * 64
        ),
    )

    assert project.status_dict()["approval_eligible"] is False
    with pytest.raises(ValueError, match="^execution_environment_changed$"):
        prepare_research_execution(project)


def test_prepare_preserves_environment_probe_unavailability(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    monkeypatch.setattr(
        "researchclaw.core.research_execution.inspect_execution_environment",
        lambda _interpreter, _distributions: (_ for _ in ()).throw(
            ValueError("execution_environment_unavailable")
        ),
    )

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        prepare_research_execution(project)


def test_external_runner_rejects_environment_drift_before_writing_result(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status = prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["environment_fingerprint"] = "0" * 64
    contract_path.write_text(json.dumps(contract, sort_keys=True, separators=(",", ":")))

    completed = subprocess.run(
        status.argv, cwd=project.root, check=False, capture_output=True, text=True
    )

    assert completed.returncode != 0
    assert "execution environment changed" in completed.stderr
    assert not (project.root / "experiment/results.json").exists()
