"""Real authoring through public CLI; setup authority stops at Stage 9."""
import hashlib
import json
import subprocess
import pytest
import copy
import os
from pathlib import Path
import sys
import sysconfig

from researchclaw.core.project import ResearchProject
from tests.codex_native.helpers import (
    build_completed_hypothesis_milestone_project,
    write_valid_fixture_artifacts,
    run_cli_json,
    valid_resource_plan,
    immutable_stage_twelve_snapshot,
)

MEAN = """def fit(train_rows, config):
    return sum(row["y"] for row in train_rows) / len(train_rows)

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
"""
LINEAR = """def fit(train_rows, config):
    mx = sum(row["x"] for row in train_rows) / len(train_rows)
    my = sum(row["y"] for row in train_rows) / len(train_rows)
    slope = sum((row["x"] - mx) * (row["y"] - my) for row in train_rows) / sum((row["x"] - mx) ** 2 for row in train_rows)
    return [slope, my - slope * mx]

def predict(model, feature_rows, config):
    return [model[0] * row["x"] + model[1] for row in feature_rows]
"""
WRAPPER = 'from researchclaw.core.agent_experiment_runtime import main\n\nif __name__ == "__main__":\n    main()\n'


@pytest.fixture(autouse=True)
def child_imports_same_tool(monkeypatch):
    # Source-tree runs need a module search path; interpreter/argv stay untouched.
    # Installed smoke can import this file with the installed researchclaw package.
    import researchclaw

    monkeypatch.setenv(
        "PYTHONPATH", str(Path(researchclaw.__file__).resolve().parent.parent)
    )


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        value if isinstance(value, str) else json.dumps(value, sort_keys=True) + "\n"
    )
    return path


def digest(root, path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def approved_design(tmp_path, capsys):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design = json.loads((project.root / "experiment/design.json").read_text())
    design["validation_type"] = "computational"
    design["method"] = {
        "datasets": ["synthetic paired scalar regression"],
        "baselines": ["training mean"],
        "split_strategy": {
            "description": "disjoint cells and paired groups",
            "isolation_key": "cell_id",
        },
        "evaluation_protocol": "fit on train only",
    }
    design["metrics"] = [
        {
            "name": "mae",
            "unit": "arbitrary_units",
            "direction": "decrease",
            "definition": "mean absolute held-out prediction error",
            "target": "<= 20",
        }
    ]
    write(project.root, "experiment/design.json", design)
    write(
        project.root,
        "data/input.csv",
        "cell_id,group_id,split_role,x,y\n"
        + "".join(
            f"C{i},G{i//2},{'train' if i < 6 else 'validation' if i < 8 else 'calibration' if i < 10 else 'test'},{i},{2*i+1}\n"
            for i in range(14)
        ),
    )
    assert run_cli_json(capsys, "stage", "validate", str(project.root), "--json")[
        "valid"
    ]
    run_cli_json(
        capsys,
        "approve",
        str(project.root),
        "--decision",
        "approve",
        "--note",
        "Synthetic test design approval",
        "--json",
    )
    return ResearchProject.open(project.root)


def author(root, project_id, source=MEAN):
    from researchclaw.core.agent_experiment import runtime_identity

    config = {
        "schema_version": 2,
        "project_id": project_id,
        "design_sha256": digest(root, "experiment/design.json"),
        "input_contract": {"required_paths": ["data/input.csv"]},
        "split_strategy": {
            "isolation_key": "cell_id",
            "overlap_policy": "disjoint",
            "groups": ["train", "validation", "calibration", "test"],
        },
        "columns": {
            "identity": "cell_id",
            "group": "group_id",
            "split": "split_role",
            "target": "y",
            "features": ["x"],
        },
        "parameters": {},
        "metrics": [{"name": "mae", "unit": "arbitrary_units"}],
    }
    contract = {
        "schema_version": 2,
        "entry_point": "experiment/code/main.py",
        "algorithm_path": "experiment/code/algorithm.py",
        "config_path": "experiment/code/config.json",
        "result_path": "experiment/results.json",
        "metrics": [
            {
                "name": "mae",
                "unit": "arbitrary_units",
                "implementation": "researchclaw.core.agent_experiment:mean_absolute_error",
            }
        ],
        "self_test": {
            "argv_suffix": [
                "--config",
                "experiment/code/self_test_config.json",
                "--self-test",
            ],
            "fixture_path": "experiment/self_test_fixture.json",
            "expected_metrics": [{"name": "mae", "expected": 0.5, "tolerance": 0.0}],
        },
        "execution": {"argv_suffix": ["--config", "experiment/code/config.json"]},
        "dependencies": [],
        "prohibitions": {
            "network_access": False,
            "external_llm_calls": False,
            "nested_agent_processes": False,
        },
    }
    files = {
        "experiment/code/main.py": WRAPPER,
        "experiment/code/algorithm.py": source,
        "experiment/code/config.json": config,
        "experiment/code/self_test_config.json": {
            "schema_version": 2,
            "fixture_path": "experiment/self_test_fixture.json",
        },
        "experiment/self_test_fixture.json": {
            "targets": [1, 3],
            "predictions": [1.5, 2.5],
        },
        "experiment/package_contract.json": contract,
        "experiment/code/README.md": "Agent-authored scalar regression, synthetic test.",
    }
    contract["runtime_sha256"] = runtime_identity()
    for path, value in files.items():
        write(root, path, value)
    manifest = {
        "schema_version": 2,
        "project_id": project_id,
        "design_sha256": config["design_sha256"],
        "validation_type": "computational",
        "entry_point": contract["entry_point"],
        "config_path": contract["config_path"],
        "files": [
            {"path": p, "role": p.rsplit("/", 1)[-1], "sha256": digest(root, p)}
            for p in files
        ],
    }
    write(root, "experiment/package_manifest.json", manifest)
    return set(files) | {"experiment/package_manifest.json"}


def stage_twelve(tmp_path, capsys, *, wrong_answer=False):
    project = approved_design(tmp_path, capsys)
    packet = run_cli_json(capsys, "stage", "prepare", str(project.root), "--json")
    outputs = author(project.root, project.state.project_id)
    if wrong_answer:
        # Author the incorrect answer before validation; never replace a validated package.
        contract = json.loads(
            (project.root / "experiment/package_contract.json").read_text()
        )
        contract["self_test"]["expected_metrics"][0]["expected"] = 999.0
        write(project.root, "experiment/package_contract.json", contract)
        manifest = json.loads(
            (project.root / "experiment/package_manifest.json").read_text()
        )
        for f in manifest["files"]:
            f["sha256"] = digest(project.root, f["path"])
        write(project.root, "experiment/package_manifest.json", manifest)
    assert set(packet["profile_context"]["agent_regression_v2_outputs"]) == outputs
    validated = run_cli_json(capsys, "stage", "validate", str(project.root), "--json")
    assert validated["valid"], validated
    project = ResearchProject.open(project.root)
    packet = run_cli_json(capsys, "stage", "prepare", str(project.root), "--json")
    from researchclaw.core.resource_planning import (
        observe_local_hardware,
        hardware_drift_warnings,
    )

    plan = valid_resource_plan(project, observe_local_hardware(project.root))
    plan["bindings"] = {
        k: {"path": p, "sha256": digest(project.root, p)}
        for k, p in {
            "design": "experiment/design.json",
            "package_manifest": "experiment/package_manifest.json",
            "config": "experiment/code/config.json",
            "hardware_profile": "scope/hardware_profile.json",
        }.items()
    }
    plan["saved_hardware_profile"] = json.loads(
        (project.root / "scope/hardware_profile.json").read_text()
    )
    plan["warnings"] = list(
        hardware_drift_warnings(
            plan["saved_hardware_profile"], plan["hardware_observation"]
        )
    )
    plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": True,
            "is_regular_file": True,
            "size_bytes": (project.root / "data/input.csv").stat().st_size,
            "sha256": digest(project.root, "data/input.csv"),
            "license_status": "confirmed",
            "preparation_note": "Synthetic fixture",
        }
    ]
    plan["tasks"][0]["estimated_duration_seconds"] = 60
    plan["tasks"][0]["depends_on"] = ["prepare_inputs"]
    plan["tasks"].insert(
        0,
        {
            "task_id": "prepare_inputs",
            "kind": "preparation",
            "depends_on": [],
            "priority": 0,
            "cpu_count": 1,
            "memory_bytes": 1,
            "gpu_count": 0,
            "temporary_disk_bytes": 1,
            "estimated_duration_seconds": 1,
        },
    )
    plan["budget"]["total_estimated_duration_seconds"] = 61
    write(project.root, "experiment/resources.json", plan)
    validated = run_cli_json(capsys, "stage", "validate", str(project.root), "--json")
    assert validated["valid"], validated
    return ResearchProject.open(project.root)


def registered_baseline(tmp_path, capsys):
    project = stage_twelve(tmp_path, capsys)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    run_cli_json(
        capsys,
        "experiment",
        "register-self-test",
        str(project.root),
        "--report",
        prepared["report_path"],
        "--confirm-self-test",
        "--json",
    )
    run_cli_json(
        capsys,
        "approve",
        str(project.root),
        "--decision",
        "approve",
        "--note",
        "Synthetic execution approval",
        "--json",
    )
    prepared = run_cli_json(
        capsys, "execution", "prepare-run", str(project.root), "--json"
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads((project.root / "experiment/results.json").read_text())
    assert result["metrics"]["primary"] == {
        "name": "mae",
        "unit": "arbitrary_units",
        "value": 18.0,
    }
    original_result = (project.root / "experiment/results.json").read_bytes()
    repeated = subprocess.run(
        prepared["argv"], cwd=prepared["cwd"], capture_output=True, timeout=60
    )
    assert repeated.returncode != 0
    assert (project.root / "experiment/results.json").read_bytes() == original_result
    run_cli_json(
        capsys,
        "execution",
        "register-result",
        str(project.root),
        "--result",
        "experiment/results.json",
        "--confirm-research-result",
        "--json",
    )
    assert ResearchProject.open(project.root).state.current_stage == 13
    return ResearchProject.open(project.root)


def test_public_agent_authored_baseline_reaches_stage_thirteen(tmp_path, capsys):
    registered_baseline(tmp_path, capsys)


def test_fitting_is_train_only_and_predictions_have_no_targets():
    from researchclaw.core.agent_experiment import decode_rows, evaluate

    columns = {
        "identity": "cell_id",
        "group": "group_id",
        "split": "split_role",
        "target": "y",
        "features": ["x"],
    }
    payload = (
        "cell_id,group_id,split_role,x,y\n"
        + "".join(
            f"C{i},G{i//2},{'train' if i < 6 else 'validation' if i < 8 else 'calibration' if i < 10 else 'test'},{i},{2*i+1}\n"
            for i in range(14)
        )
    ).encode()
    partitions, summary = decode_rows(payload, columns)
    changed = copy.deepcopy(partitions)
    for role in ("validation", "calibration", "test"):
        for row in changed[role]:
            row["y"] = -999
    for source, model, predictions, metric in (
        (MEAN, 6.0, [6.0] * 4, 18.0),
        (LINEAR, [2.0, 1.0], [21.0, 23.0, 25.0, 27.0], 0.0),
    ):
        assert evaluate(source, partitions, columns, {}) == (model, predictions, metric)
        assert evaluate(source, changed, columns, {})[:2] == (model, predictions)
    leaking = LINEAR.replace('model[0] * row["x"] + model[1]', 'row["y"]')
    with pytest.raises(KeyError):
        evaluate(leaking, partitions, columns, {})
    assert summary["roles"]["train"] == {"cell_count": 6, "group_count": 3}


@pytest.mark.parametrize(
    "source",
    [
        "import os\n" + MEAN,
        MEAN.replace('sum(row["y"] for row in train_rows)', 'open("secret")'),
        MEAN.replace(
            "return [model for row in feature_rows]", "return model.__class__"
        ),
        MEAN + '\nprint("executed")\n',
        MEAN.replace("return [model for row in feature_rows]", 'return eval("1")'),
        MEAN.replace(
            "return [model for row in feature_rows]", "while True:\n        pass"
        ),
    ],
)
def test_static_algorithm_rejects_capabilities(source):
    from researchclaw.core.agent_experiment import validate_algorithm

    with pytest.raises(ValueError):
        validate_algorithm(source)


def test_numerical_subset_rejects_collection_amplification_and_large_powers():
    from researchclaw.core.agent_experiment import evaluate, validate_algorithm

    with pytest.raises(ValueError):
        validate_algorithm(
            MEAN.replace(
                "return [model for row in feature_rows]",
                "return [10 ** 1000000000 for row in feature_rows]",
            )
        )
    source = MEAN.replace(
        "return [model for row in feature_rows]",
        "values = [model]\n    return values * 2",
    )
    with pytest.raises(ValueError):
        evaluate(
            source,
            {"train": [{"y": 1}], "test": [{"x": 1, "y": 3}, {"x": 2, "y": 5}]},
            {"target": "y", "features": ["x"]},
            {},
        )


@pytest.mark.parametrize("expression", ["a == b", "min(a, b)", "max([a, b])"])
def test_recursive_collection_comparisons_reject_within_watchdog(expression):
    source = f"""def fit(train_rows, config):
    a = [0]
    b = [0]
    for row in train_rows:
        a = [a, a]
        b = [b, b]
    comparison = {expression}
    return 0

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
"""
    probe = f"""from researchclaw.core.agent_experiment import evaluate
try:
    evaluate({source!r}, {{"train": [{{"y": 1}}] * 28,
             "test": [{{"x": 1, "y": 1}}]}},
             {{"target": "y", "features": ["x"]}}, {{}})
except ValueError as error:
    assert "comparison requires finite numbers" in str(error), error
    print("rejected before recursive comparison")
else:
    raise AssertionError("recursive collection comparison was accepted")
"""
    # A parent-owned watchdog also bounds the failing pre-fix C-level operation.
    completed = subprocess.run(
        [sys.executable, "-P", "-c", probe],
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "rejected before recursive comparison"


@pytest.mark.parametrize(
    "operation",
    [
        "ignored = {a: 1}",
        "ignored = {a: 1, b: 2}",
        "ignored = {0: 1}[a]",
        "table = {}\n    for table[a] in train_rows:\n        ignored = 0",
    ],
    ids=["construction", "collision", "lookup", "loop-assignment"],
)
def test_recursive_dictionary_keys_reject_within_watchdog(operation):
    source = f"""def fit(train_rows, config):
    a = (0,)
    b = (0,)
    for row in train_rows:
        a = (a, a)
        b = (b, b)
    {operation}
    return 0

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
"""
    probe = f"""from researchclaw.core.agent_experiment import evaluate
try:
    evaluate({source!r}, {{"train": [{{"y": 1}}] * 32,
             "test": [{{"x": 1, "y": 1}}]}},
             {{"target": "y", "features": ["x"]}}, {{}})
except ValueError as error:
    assert "key requires a bounded string or finite number" in str(error), error
    print("rejected before implicit hashing")
else:
    raise AssertionError("recursive dictionary key was accepted")
"""
    completed = subprocess.run(
        [sys.executable, "-P", "-c", probe],
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "rejected before implicit hashing"


def test_dictionary_unpacking_is_outside_authored_subset():
    from researchclaw.core.agent_experiment import validate_algorithm

    source = MEAN.replace(
        'return sum(row["y"] for row in train_rows) / len(train_rows)',
        "ignored = {**config}\n    return 0",
    )
    with pytest.raises(ValueError, match="dictionary unpacking prohibited"):
        validate_algorithm(source)


def test_dictionary_direct_assignment_remains_prohibited():
    from researchclaw.core.agent_experiment import validate_algorithm

    source = MEAN.replace(
        'return sum(row["y"] for row in train_rows) / len(train_rows)',
        'model = {}\n    model["bias"] = 0\n    return model',
    )
    with pytest.raises(ValueError, match="assignments must be local names"):
        validate_algorithm(source)


def test_model_dictionary_and_row_indexing_remain_supported():
    from researchclaw.core.agent_experiment import evaluate

    source = """def fit(train_rows, config):
    numeric = {1: train_rows[0]["y"]}
    return {"bias": numeric[1], "scale": config["scale"]}

def predict(model, feature_rows, config):
    return [model["bias"] + model["scale"] * row["x"] for row in feature_rows]
"""
    assert evaluate(
        source,
        {"train": [{"y": 1}], "test": [{"x": 2, "y": 7}]},
        {"target": "y", "features": ["x"]},
        {"scale": 3},
    ) == ({"bias": 1, "scale": 3}, [7], 0)


def test_numeric_comparisons_and_extrema_remain_supported():
    from researchclaw.core.agent_experiment import evaluate

    source = """def fit(train_rows, config):
    low = min(row["y"] for row in train_rows)
    high = max(low, 3)
    return high if 0 < low <= high else 0

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
"""
    assert evaluate(
        source,
        {"train": [{"y": 1}, {"y": 2}], "test": [{"x": 1, "y": 3}]},
        {"target": "y", "features": ["x"]},
        {},
    ) == (3, [3], 0)


def test_model_serialization_has_a_size_and_depth_budget():
    from researchclaw.core.agent_experiment import evaluate

    source = """def fit(train_rows, config):
    model = [0]
    for row in train_rows:
        model = [model, model]
    return model

def predict(model, feature_rows, config):
    return [0 for row in feature_rows]
"""
    # Only 16 source iterations; naive JSON expansion doubles shared subtrees.
    with pytest.raises(ValueError, match="model serialization budget"):
        evaluate(
            source,
            {"train": [{"y": 1}] * 16, "test": [{"x": 1, "y": 1}]},
            {"target": "y", "features": ["x"]},
            {},
        )


def test_wrong_known_answer_does_not_publish(tmp_path, capsys):
    project = stage_twelve(tmp_path, capsys, wrong_answer=True)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0
    assert "known answer failed" in completed.stderr
    assert not (project.root / prepared["report_path"]).exists()
    assert not (project.root / "experiment/results.json").exists()


@pytest.mark.parametrize(
    "path",
    [
        "experiment/code/algorithm.py",
        "experiment/code/config.json",
        "experiment/package_contract.json",
        "experiment/self_test_fixture.json",
        "data/input.csv",
    ],
)
def test_prepared_execution_rejects_tampered_bytes_without_result(
    tmp_path, capsys, path
):
    project = stage_twelve(tmp_path, capsys)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    run_cli_json(
        capsys,
        "experiment",
        "register-self-test",
        str(project.root),
        "--report",
        prepared["report_path"],
        "--confirm-self-test",
        "--json",
    )
    run_cli_json(
        capsys,
        "approve",
        str(project.root),
        "--decision",
        "approve",
        "--note",
        "Synthetic execution approval",
        "--json",
    )
    prepared = run_cli_json(
        capsys, "execution", "prepare-run", str(project.root), "--json"
    )
    with (project.root / path).open("a") as f:
        f.write("\n")
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0
    assert not (project.root / "experiment/results.json").exists()
    assert ResearchProject.open(project.root).state.current_stage == 12


def test_no_execution_approval_and_no_overwrite(tmp_path, capsys):
    from tests.codex_native.helpers import run_cli

    project = stage_twelve(tmp_path, capsys)
    assert run_cli("execution", "prepare-run", str(project.root), "--json") != 0
    capsys.readouterr()
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    actual_run = [*prepared["argv"][:4], "--config", "experiment/code/config.json"]
    completed = subprocess.run(
        actual_run, cwd=project.root, capture_output=True, text=True, timeout=60
    )
    assert completed.returncode != 0
    assert not (project.root / "experiment/results.json").exists()
    assert (
        subprocess.run(
            prepared["argv"], cwd=prepared["cwd"], capture_output=True, timeout=60
        ).returncode
        == 0
    )
    original = (project.root / prepared["report_path"]).read_bytes()
    assert (
        subprocess.run(
            prepared["argv"], cwd=prepared["cwd"], capture_output=True, timeout=60
        ).returncode
        != 0
    )
    assert (project.root / prepared["report_path"]).read_bytes() == original


def test_changed_interpreter_cannot_publish_self_test(tmp_path, capsys):
    project = stage_twelve(tmp_path, capsys)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    alternate = tmp_path / "changed-python"
    created = subprocess.run(
        [
            prepared["argv"][0],
            "-m",
            "venv",
            "--without-pip",
            "--system-site-packages",
            "--copies",
            str(alternate),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert created.returncode == 0, created.stderr
    launcher = alternate / "bin/python"
    # Nested venvs inherit the base installation's site-packages, not necessarily
    # the parent test venv's dependencies. Retain those paths only for this child.
    child_environment = os.environ.copy()
    child_environment["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys(
            (
                os.environ["PYTHONPATH"],
                sysconfig.get_path("purelib"),
                sysconfig.get_path("platlib"),
            )
        )
    )
    probe = subprocess.run(
        [
            str(launcher),
            "-P",
            "-c",
            "import encodings, researchclaw.core.agent_experiment_runtime; print('ready')",
        ],
        cwd=prepared["cwd"],
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "ready"
    changed_argv = [str(launcher), *prepared["argv"][1:]]
    completed = subprocess.run(
        changed_argv,
        cwd=prepared["cwd"],
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0
    assert not (project.root / prepared["report_path"]).exists()
    error = completed.stderr.strip().splitlines()[-1]
    assert error in {
        "ValueError: execution environment changed",
        "ValueError: execution_environment_unavailable",
    }, completed.stderr
    assert "agent_experiment_runtime.py" in completed.stderr
    if error == "ValueError: execution_environment_unavailable":
        # A copied non-framework interpreter can be runnable but fail OS image
        # attestation. Require that exact inspector rejection, not startup errors.
        assert "execution_environment.py" in completed.stderr
        assert "in inspect_execution_environment" in completed.stderr


def test_non_authoritative_wrapper_launch_cannot_publish(tmp_path, capsys):
    project = stage_twelve(tmp_path, capsys)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    substitute = [
        prepared["argv"][0],
        "-P",
        "experiment/code/main.py",
        *prepared["argv"][4:],
    ]
    completed = subprocess.run(
        substitute, cwd=prepared["cwd"], capture_output=True, text=True, timeout=60
    )
    assert completed.returncode != 0
    assert not (project.root / prepared["report_path"]).exists()


@pytest.mark.parametrize("filename", ["researchclaw.py", "main.py"])
def test_project_module_shadow_cannot_execute_before_runtime_validation(
    tmp_path, capsys, filename
):
    project = stage_twelve(tmp_path, capsys)
    prepared = run_cli_json(
        capsys, "experiment", "prepare-self-test", str(project.root), "--json"
    )
    marker = project.root / "shadow-executed"
    write(
        project.root,
        "experiment/code/" + filename,
        f"open({str(marker)!r}, 'w').write('unsafe import')\n",
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0
    assert not marker.exists()
    assert not (project.root / prepared["report_path"]).exists()


@pytest.mark.parametrize(
    "case", ["metric", "runtime", "prohibitions", "extra", "missing"]
)
def test_static_v2_contract_rejects_invalid_authoring(tmp_path, capsys, case):
    from researchclaw.core.agent_experiment import validate_package

    project = approved_design(tmp_path, capsys)
    run_cli_json(capsys, "stage", "prepare", str(project.root), "--json")
    author(project.root, project.state.project_id)
    path = "experiment/package_contract.json"
    contract = json.loads((project.root / path).read_text())
    if case == "metric":
        contract["metrics"][0]["name"] = "rmse"
    elif case == "runtime":
        contract["runtime_sha256"]["agent_experiment_runtime.py"] = "0" * 64
    elif case == "prohibitions":
        contract["prohibitions"]["network_access"] = 0
    elif case == "extra":
        contract["undeclared"] = True
    else:
        del contract["algorithm_path"]
    write(project.root, path, contract)
    manifest = json.loads(
        (project.root / "experiment/package_manifest.json").read_text()
    )
    for f in manifest["files"]:
        f["sha256"] = digest(project.root, f["path"])
    write(project.root, "experiment/package_manifest.json", manifest)
    with pytest.raises(ValueError):
        validate_package(project.root)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace("G1,validation", "G0,validation"),
        lambda s: s.replace("x,y", "x,y,extra").replace("0,1\n", "0,1,9\n"),
        lambda s: s.replace("x,y", "x"),
        lambda s: s.replace("0,1\n", "nan,1\n"),
        lambda s: s.replace("C1,", "C0,"),
    ],
)
def test_csv_safety(mutate):
    from researchclaw.core.agent_experiment import decode_rows

    source = "cell_id,group_id,split_role,x,y\nC0,G0,train,0,1\nC1,G1,validation,1,3\nC2,G2,calibration,2,5\nC3,G3,test,3,7\n"
    with pytest.raises(ValueError):
        decode_rows(
            mutate(source).encode(),
            {
                "identity": "cell_id",
                "group": "group_id",
                "split": "split_role",
                "target": "y",
                "features": ["x"],
            },
        )


def author_candidate(project):
    root = project.root
    prefix = "refinement/candidates/candidate-001/"
    sources = {
        "code/model.py": "experiment/code/main.py",
        "code/algorithm.py": "experiment/code/algorithm.py",
        "config/config.json": "experiment/code/config.json",
        "tests/self_test_config.json": "experiment/code/self_test_config.json",
        "tests/self_test_fixture.json": "experiment/self_test_fixture.json",
        "package_metadata/package_contract.json": "experiment/package_contract.json",
        "package_metadata/package_manifest.json": "experiment/package_manifest.json",
    }
    contract = json.loads((root / "experiment/package_contract.json").read_text())
    contract.update(
        entry_point="code/model.py",
        algorithm_path="code/algorithm.py",
        config_path="config/config.json",
        result_path="results.json",
    )
    contract["self_test"].update(
        argv_suffix=["--config", "tests/self_test_config.json", "--self-test"],
        fixture_path="tests/self_test_fixture.json",
    )
    contract["execution"] = {"argv_suffix": ["--config", "config/config.json"]}
    for dest, src in sources.items():
        if dest == "package_metadata/package_manifest.json":
            continue
        payload = (root / src).read_text()
        if dest == "code/algorithm.py":
            payload = LINEAR
        elif dest == "package_metadata/package_contract.json":
            payload = contract
        elif dest == "tests/self_test_config.json":
            payload = {
                "schema_version": 2,
                "fixture_path": "tests/self_test_fixture.json",
            }
        write(root, prefix + dest, payload)
    manifest = json.loads((root / "experiment/package_manifest.json").read_text())
    manifest.update(
        entry_point="code/model.py",
        config_path="config/config.json",
        files=[
            {
                "path": p,
                "role": p.rsplit("/", 1)[-1],
                "sha256": digest(root, prefix + p),
            }
            for p in sources
            if p != "package_metadata/package_manifest.json"
        ],
    )
    write(root, prefix + "package_metadata/package_manifest.json", manifest)
    changed = [
        prefix + p
        for p, src in sources.items()
        if digest(root, prefix + p) != digest(root, src)
    ]
    return sources, changed


def test_public_candidate_fitted_line_preserves_baseline(tmp_path, capsys):
    from tests.codex_native.test_refinement import valid_envelope, valid_decision_record
    from tests.codex_native.test_stage13_multi_agent_e2e import _register_assessments

    project = registered_baseline(tmp_path, capsys)
    original = immutable_stage_twelve_snapshot(project)
    write(project.root, "refinement/envelope.json", valid_envelope())
    run_cli_json(
        capsys,
        "refinement",
        "prepare-session",
        str(project.root),
        "--envelope",
        "refinement/envelope.json",
        "--json",
    )
    # Synthetic council records exercise protocol gates, not scientific endorsement.
    _register_assessments(capsys, project, submission_prefix="synthetic")
    changed = [
        "refinement/candidates/candidate-001/" + path
        for path in (
            "code/algorithm.py",
            "tests/self_test_config.json",
            "package_metadata/package_contract.json",
            "package_metadata/package_manifest.json",
        )
    ]
    decision = valid_decision_record(project, change_paths=changed)
    decision["rationale"] = ["Synthetic protocol test; not scientific approval."]
    for vote in decision["final_votes"]:
        vote["rationale"] = ["Synthetic protocol test; not scientific approval."]
    write(project.root, "submissions/synthetic-decision.json", decision)
    run_cli_json(
        capsys,
        "refinement",
        "register-decision",
        str(project.root),
        "--decision",
        "submissions/synthetic-decision.json",
        "--json",
    )
    sources, actual_changed = author_candidate(project)
    assert actual_changed == changed
    project = ResearchProject.open(project.root)
    decision_path = (
        sorted(project.root.glob("refinement/deliberations/round-*/decision.json"))[-1]
        .relative_to(project.root)
        .as_posix()
    )
    baseline_path = next(
        p
        for p in project.state.artifacts
        if p.startswith(".researchclaw/evidence/manifests/")
    )

    def ref(p):
        return {
            "path": p,
            "sha256": digest(project.root, p),
            "size": (project.root / p).stat().st_size,
        }

    prefix = "refinement/candidates/candidate-001/"
    config = json.loads((project.root / "experiment/code/config.json").read_text())
    package = json.loads(
        (project.root / "experiment/package_contract.json").read_text()
    )
    manifest = {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "session_id": json.loads(
            (project.root / "refinement/session.json").read_text()
        )["session_id"],
        "candidate_id": "candidate-001",
        "producer": "implementation-agent",
        "created_at": "2026-09-01T00:00:00+00:00",
        "decision": ref(decision_path),
        "change_request": {"paths": changed},
        "baseline_manifest": ref(baseline_path),
        "baseline_package": {
            "contract_sha256": digest(project.root, "experiment/package_contract.json"),
            "manifest_sha256": digest(project.root, "experiment/package_manifest.json"),
            "config_sha256": digest(project.root, "experiment/code/config.json"),
        },
        "unchanged_declarations": {
            "input_paths": ["data/input.csv"],
            "input_contract": config["input_contract"],
            "split_strategy": config["split_strategy"],
            "metrics": package["metrics"],
        },
        "package_contract": "package_metadata/package_contract.json",
        "entry_point": "code/model.py",
        "files": [
            {
                **ref(prefix + p),
                "provenance": {"kind": "stage12_evidence", "source_path": src},
            }
            for p, src in sources.items()
        ],
    }
    manifest_path = write(
        project.root,
        prefix + "package_metadata/manifest.json",
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
    )
    run_cli_json(
        capsys,
        "refinement",
        "register-candidate",
        str(project.root),
        "--manifest",
        manifest_path,
        "--json",
    )
    prepared = run_cli_json(
        capsys,
        "refinement",
        "prepare-self-test",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--json",
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    run_cli_json(
        capsys,
        "refinement",
        "register-self-test",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--report",
        prepared["report_path"],
        "--confirm-refinement-self-test",
        "--json",
    )
    prepared = run_cli_json(
        capsys,
        "refinement",
        "prepare-run",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--json",
    )
    completed = subprocess.run(
        prepared["argv"],
        cwd=prepared["cwd"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads((project.root / prepared["result_path"]).read_text())
    assert result["metrics"]["primary"]["value"] == pytest.approx(0.0, abs=1e-9)
    run_cli_json(
        capsys,
        "refinement",
        "register-result",
        str(project.root),
        "--candidate-id",
        "candidate-001",
        "--result",
        prepared["result_path"],
        "--confirm-refinement-result",
        "--json",
    )
    assert (
        immutable_stage_twelve_snapshot(ResearchProject.open(project.root)) == original
    )
    assert ResearchProject.open(project.root).state.current_stage == 13
