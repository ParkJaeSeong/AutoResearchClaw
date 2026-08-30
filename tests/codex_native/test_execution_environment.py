"""Tests for the closed execution-environment evidence contract."""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

import researchclaw.core.experiment_package_contract as package_contract
from researchclaw.core.execution_environment import (
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
    assert dict(environment.dependencies) == {"pytest": environment.dependencies["pytest"]}
    assert "researchclaw" not in (project.root / package.entry_point).read_text()


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

    assert project.status_dict()["approval_eligible"] is False
    with pytest.raises(ValueError, match="^execution_environment_changed$"):
        prepare_research_execution(project)
