"""Tests for the closed execution-environment evidence contract."""

from dataclasses import replace
import json
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
        process_image="/absolute/python-image",
        process_image_identity={"sha256": "b" * 64},
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
    assert payload["process_image"] == "/absolute/python-image"


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
    venv.EnvBuilder(with_pip=False, symlinks=False).create(environment_root)
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
    inspection = subprocess.run(
        [
            str(interpreter),
            "-c",
            "from pathlib import Path; import sys; "
            "from researchclaw.core.execution_environment import inspect_execution_environment; "
            "print(inspect_execution_environment(Path(sys.executable).resolve(strict=True), ()).fingerprint)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert inspection.returncode == 0, inspection.stderr
    assert report["environment_fingerprint"] == inspection.stdout.strip()


def test_generated_self_test_matches_a_symlink_venv_interpreter_contract(tmp_path):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(environment_root)
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
    inspection = subprocess.run(
        [
            str(interpreter),
            "-c",
            "from pathlib import Path; import json, sys; "
            "from researchclaw.core.execution_environment import inspect_execution_environment; "
            "environment = inspect_execution_environment(Path(sys.executable).resolve(strict=True), ()); "
            "print(json.dumps({'fingerprint': environment.fingerprint, 'launcher': environment.launcher}))",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    launcher_bound_inspection = subprocess.run(
        [
            str(interpreter),
            "-c",
            "from experiment.code.main import execution_environment_fingerprint; "
            "print(execution_environment_fingerprint([], "
            f"{str(interpreter)!r}))",
        ],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert inspection.returncode == 0, inspection.stderr
    assert launcher_bound_inspection.returncode == 0, launcher_bound_inspection.stderr
    report = json.loads((project.root / SELF_TEST_REPORT_PATH).read_text())
    observed = json.loads(inspection.stdout)
    assert observed["launcher"] == str(interpreter)
    assert report["environment_fingerprint"] == observed["fingerprint"]
    assert launcher_bound_inspection.stdout.strip() == observed["fingerprint"]


def test_inspection_rejects_repointed_sys_executable(tmp_path, monkeypatch):
    requested = _resolved_interpreter()
    alternate = tmp_path / "python"
    shutil.copy2(requested, alternate)
    alternate.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(alternate))

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(requested, ())


def test_inspection_rejects_an_alternate_regular_python(tmp_path):
    alternate = tmp_path / "python"
    shutil.copy2(_resolved_interpreter(), alternate)
    alternate.chmod(0o755)

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(alternate, ())


def test_inspection_rejects_a_venv_shaped_symlink_entrypoint(tmp_path):
    environment_root = tmp_path / "environment"
    (environment_root / "bin").mkdir(parents=True)
    (environment_root / "pyvenv.cfg").write_text("home = /not/authoritative\n")
    interpreter = environment_root / "bin/python"
    interpreter.symlink_to(_resolved_interpreter())

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(interpreter, ())


def test_linux_process_image_helper_reads_proc_self_exe(monkeypatch):
    observed: list[str] = []

    def readlink(path):
        observed.append(path)
        return "/opt/python/bin/python3.11"

    monkeypatch.setattr(execution_environment.os, "readlink", readlink)

    assert execution_environment._linux_proc_self_executable() == Path(
        "/opt/python/bin/python3.11"
    )
    assert observed == ["/proc/self/exe"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS process attestors")
def test_macos_process_image_attestors_agree_on_the_loaded_image():
    proc_path, dyld_path = execution_environment._macos_process_image_paths()

    assert proc_path == dyld_path
    assert proc_path.is_absolute()
    assert proc_path.resolve(strict=True) == proc_path
    assert proc_path.is_file()


def test_macos_process_image_attestation_rejects_disagreement(monkeypatch):
    interpreter = _resolved_interpreter()
    monkeypatch.setattr(execution_environment.sys, "platform", "darwin")
    monkeypatch.setattr(
        execution_environment,
        "_macos_process_image_paths",
        lambda: (interpreter, interpreter.with_name("different-image")),
    )

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        execution_environment._attested_process_image()


def test_inspection_rejects_held_descriptor_identity_drift(monkeypatch):
    original_identity = execution_environment._descriptor_identity
    calls: dict[int, int] = {}

    def drifting_identity(descriptor):
        identity = original_identity(descriptor)
        calls[descriptor] = calls.get(descriptor, 0) + 1
        if calls[descriptor] > 1:
            return {**identity, "sha256": "0" * 64}
        return identity

    monkeypatch.setattr(execution_environment, "_descriptor_identity", drifting_identity)

    with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
        inspect_execution_environment(_resolved_interpreter(), ())


@pytest.mark.parametrize("replacement_kind", ["regular", "symlink", "missing"])
def test_copied_venv_launcher_replacement_after_capture_is_rejected(
    tmp_path, replacement_kind
):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False, symlinks=False).create(environment_root)
    interpreter = environment_root / "bin/python"
    replacement = environment_root / "bin/replacement"
    replacement.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
    replacement.chmod(0o755)
    source = """
import os
from pathlib import Path
import sys
import researchclaw.core.execution_environment as execution_environment

original_python_version = execution_environment.runtime_platform.python_version
replacement = Path(sys.argv[1])
replacement_kind = sys.argv[2]

def replace_launcher():
    interpreter = Path(sys.executable)
    if replacement_kind == "regular":
        os.replace(replacement, interpreter)
    else:
        saved_interpreter = interpreter.with_name("python.saved")
        os.replace(interpreter, saved_interpreter)
        if replacement_kind == "symlink":
            interpreter.symlink_to(saved_interpreter)
    return original_python_version()

execution_environment.runtime_platform.python_version = replace_launcher
execution_environment.inspect_execution_environment(
    Path(sys.executable).resolve(strict=True), ()
)
"""

    completed = subprocess.run(
        [str(interpreter), "-c", source, str(replacement), replacement_kind],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "execution_environment_unavailable" in completed.stderr


@pytest.mark.parametrize("replacement_kind", ["regular", "symlink", "missing"])
def test_framework_process_image_final_path_revalidation_rejects_replacement(
    tmp_path, replacement_kind
):
    launcher = tmp_path / "python-launcher"
    process_image = tmp_path / "Python"
    saved_process_image = tmp_path / "Python.saved"
    shutil.copy2(_resolved_interpreter(), launcher)
    shutil.copy2(_resolved_interpreter(), process_image)
    launcher.chmod(0o755)
    process_image.chmod(0o755)
    paths = execution_environment._CurrentRuntimePaths(
        interpreter=launcher,
        process_image=process_image,
        base_interpreter=launcher,
        venv_prefix=None,
    )
    verified = execution_environment._open_runtime_executables(paths)
    try:
        process_image.rename(saved_process_image)
        if replacement_kind == "regular":
            process_image.write_text("#!/bin/sh\nexit 92\n", encoding="utf-8")
            process_image.chmod(0o755)
        elif replacement_kind == "symlink":
            process_image.symlink_to(saved_process_image)

        with pytest.raises(ValueError, match="^execution_environment_unavailable$"):
            execution_environment._revalidate_authoritative_paths(paths, verified)
    finally:
        for item in verified.values():
            execution_environment.os.close(item.descriptor)


def test_authoritative_path_aba_restoring_the_held_inode_is_accepted(tmp_path):
    launcher = tmp_path / "python-launcher"
    process_image = tmp_path / "Python"
    saved_process_image = tmp_path / "Python.saved"
    attacker = tmp_path / "Python.attacker"
    shutil.copy2(_resolved_interpreter(), launcher)
    shutil.copy2(_resolved_interpreter(), process_image)
    launcher.chmod(0o755)
    process_image.chmod(0o755)
    attacker.write_text("#!/bin/sh\nexit 93\n", encoding="utf-8")
    attacker.chmod(0o755)
    paths = execution_environment._CurrentRuntimePaths(
        interpreter=launcher,
        process_image=process_image,
        base_interpreter=launcher,
        venv_prefix=None,
    )
    verified = execution_environment._open_runtime_executables(paths)
    try:
        process_image.rename(saved_process_image)
        attacker.rename(process_image)
        process_image.unlink()
        saved_process_image.rename(process_image)

        execution_environment._revalidate_authoritative_paths(paths, verified)
    finally:
        for item in verified.values():
            execution_environment.os.close(item.descriptor)


def test_current_copied_venv_interpreter_preserves_private_distribution(tmp_path):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False, symlinks=False).create(environment_root)
    interpreter = environment_root / "bin/python"
    site_packages = next((environment_root / "lib").glob("python*/site-packages"))
    metadata = site_packages / "private_probe-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: private-probe\nVersion: 1.2.3\n",
        encoding="utf-8",
    )
    source = """
import json
from pathlib import Path
import sys
from researchclaw.core.execution_environment import inspect_execution_environment

environment = inspect_execution_environment(
    Path(sys.executable).resolve(strict=True), ("private-probe",)
)
print(json.dumps({"interpreter": environment.interpreter, "dependencies": dict(environment.dependencies)}))
"""

    completed = subprocess.run(
        [str(interpreter), "-c", source],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["interpreter"] == str(interpreter.resolve(strict=True))
    assert payload["dependencies"] == {"private-probe": "1.2.3"}


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
    assert not (project.root / "experiment/execution_contract.json").exists()


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


def test_external_runner_rejects_a_replaced_contract_interpreter_path(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status = prepare_research_execution(project)
    alternate = tmp_path / "alternate-python"
    shutil.copy2(_resolved_interpreter(), alternate)
    alternate.chmod(0o755)
    contract_path = project.root / "experiment/execution_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["argv"][0] = str(alternate)
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":"))
    )

    completed = subprocess.run(
        status.argv, cwd=project.root, check=False, capture_output=True, text=True
    )

    assert completed.returncode != 0
    assert "execution environment changed" in completed.stderr
    assert not (project.root / "experiment/results.json").exists()


def test_generated_runner_revalidates_its_copied_venv_launcher_path(tmp_path):
    environment_root = tmp_path / "environment"
    venv.EnvBuilder(
        with_pip=False, symlinks=False, system_site_packages=True
    ).create(environment_root)
    interpreter = environment_root / "bin/python"
    project_root = tmp_path / "project"
    distribution_root = tmp_path / "distributions"
    hook_root = tmp_path / "hook"
    replacement = environment_root / "bin/replacement"
    metadata = distribution_root / "path_reopen_probe-1.2.3.dist-info/METADATA"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "Metadata-Version: 2.1\nName: path-reopen-probe\nVersion: 1.2.3\n",
        encoding="utf-8",
    )
    source = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

project_root = Path(sys.argv[1])
distribution_root = Path(sys.argv[2])
hook_root = Path(sys.argv[3])
replacement = Path(sys.argv[4])
sys.path.insert(0, str(distribution_root))
inherited_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = os.pathsep.join(
    item for item in (str(distribution_root), inherited_pythonpath) if item
)

from researchclaw.core.approval import approve_current_gate
from researchclaw.core.execution_gate import recheck_execution_readiness
from researchclaw.core.project import ResearchProject
from researchclaw.core.research_execution import prepare_research_execution
from tests.codex_native.helpers import (
    build_stage_twelve_project,
    register_stage_twelve_known_answer_self_test,
)

project, declared_input = build_stage_twelve_project(
    project_root, readiness="ready_for_execution", register_self_test=False
)
package_contract_path = project.root / "experiment/package_contract.json"
package_contract = json.loads(package_contract_path.read_text(encoding="utf-8"))
package_contract["dependencies"] = ["path-reopen-probe"]
package_contract_path.write_text(
    json.dumps(package_contract, sort_keys=True) + "\n", encoding="utf-8"
)
register_stage_twelve_known_answer_self_test(project)
project = ResearchProject.open(project.root)
declared_input.parent.mkdir(parents=True, exist_ok=True)
declared_input.write_bytes(b"approved research input\n")
recheck_execution_readiness(project)
project = ResearchProject.open(project.root)
approve_current_gate(project, "approve", "Explicit execution approved")
project = ResearchProject.open(project.root)
status = prepare_research_execution(project)

hook_root.mkdir(parents=True)
(hook_root / "sitecustomize.py").write_text(
    "import importlib.metadata as metadata\n"
    "import os\n"
    "from pathlib import Path\n"
    "original_version = metadata.version\n"
    "replaced = False\n"
    "def replacing_version(name):\n"
    "    global replaced\n"
    "    if not replaced:\n"
    "        replaced = True\n"
    "        os.replace(Path(os.environ['PATH_REOPEN_REPLACEMENT']), "
    "Path(os.environ['PATH_REOPEN_INTERPRETER']))\n"
    "    return original_version(name)\n"
    "metadata.version = replacing_version\n",
    encoding="utf-8",
)
replacement.write_text("#!/bin/sh\nexit 94\n", encoding="utf-8")
replacement.chmod(0o755)
runner_environment = dict(os.environ)
runner_environment["PYTHONPATH"] = os.pathsep.join(
    item
    for item in (str(hook_root), str(distribution_root), inherited_pythonpath)
    if item
)
runner_environment["PATH_REOPEN_REPLACEMENT"] = str(replacement)
runner_environment["PATH_REOPEN_INTERPRETER"] = status.argv[0]
completed = subprocess.run(
    status.argv,
    cwd=project.root,
    env=runner_environment,
    check=False,
    capture_output=True,
    text=True,
)
print(
    json.dumps(
        {
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "result_exists": (project.root / "experiment/results.json").exists(),
        }
    )
)
'''

    completed = subprocess.run(
        [
            str(interpreter),
            "-c",
            source,
            str(project_root),
            str(distribution_root),
            str(hook_root),
            str(replacement),
        ],
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["returncode"] != 0
    assert "execution environment changed" in outcome["stderr"]
    assert outcome["result_exists"] is False
