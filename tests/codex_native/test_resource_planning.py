import copy
import hashlib
import json
from pathlib import Path

import pytest

from researchclaw.core.models import StageStatus
from researchclaw.core.project import ResearchProject
from researchclaw.core.resource_planning import (
    HardwareObservation,
    observe_local_hardware,
    validate_stage_eleven,
    validate_resource_plan_structure,
)
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import (
    build_completed_validation_design_project,
    valid_resource_plan,
    write_valid_fixture_artifacts,
)


_BINDING_PATHS = {
    "design": "experiment/design.json",
    "package_manifest": "experiment/package_manifest.json",
    "config": "experiment/code/config.json",
    "hardware_profile": "scope/hardware_profile.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_plan(project, *, readiness="ready_for_execution"):
    observation = observe_local_hardware(project.root)
    plan = valid_resource_plan(project, observation, readiness=readiness)
    plan["bindings"] = {
        name: {"path": path, "sha256": _sha256(project.root / path)}
        for name, path in _BINDING_PATHS.items()
    }
    plan["saved_hardware_profile"] = json.loads(
        (project.root / "scope/hardware_profile.json").read_text(encoding="utf-8")
    )
    return plan


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def stage_11_project(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    return ResearchProject.open(project.root)


@pytest.fixture
def ready_plan(stage_11_project):
    return _semantic_plan(stage_11_project)


@pytest.fixture
def missing_plan(stage_11_project):
    plan = _semantic_plan(stage_11_project, readiness="needs_input")
    plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": False,
            "is_regular_file": False,
            "size_bytes": 0,
            "sha256": None,
            "license_status": "unconfirmed",
            "preparation_note": "Provide the licensed input at data/input.csv.",
        }
    ]
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
    plan["tasks"][1]["depends_on"] = ["prepare_inputs"]
    plan["budget"]["total_estimated_duration_seconds"] = 2
    plan["unmet_prerequisites"] = ["Provide the licensed input at data/input.csv."]
    return plan


def test_observe_local_hardware_reports_passive_non_negative_facts(tmp_path):
    observed = observe_local_hardware(tmp_path)

    assert observed.logical_cpu_count >= 1
    assert observed.total_memory_bytes >= 0
    assert observed.free_disk_bytes >= 0
    assert observed.platform
    assert observed.architecture
    assert observed.method == "python_stdlib_passive"


@pytest.fixture
def resource_plan(tmp_path):
    project = ResearchProject.create(tmp_path / "project", "Resource planning", "materials_ai")
    observation = HardwareObservation(
        logical_cpu_count=1,
        total_memory_bytes=1,
        free_disk_bytes=1,
        platform="test",
        architecture="test",
        gpu_available=None,
        method="python_stdlib_passive",
        observed_at="2026-08-29T00:00:00+00:00",
    )
    return valid_resource_plan(project, observation)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda plan: plan.update(extra=True), "unknown_field"),
        (lambda plan: plan["tasks"].append(dict(plan["tasks"][0])), "duplicate_task_id"),
        (lambda plan: plan["tasks"][0].update(depends_on=["missing"]), "missing_dependency"),
        (lambda plan: plan["tasks"][0].update(memory_bytes=-1), "invalid_resource_value"),
        (lambda plan: plan["budget"].update(max_parallel_tasks=2), "unsupported_parallelism"),
    ],
)
def test_closed_plan_rejects_structural_errors(resource_plan, mutation, code):
    plan = copy.deepcopy(resource_plan)
    mutation(plan)

    assert code in {issue.code for issue in validate_resource_plan_structure(plan).issues}


def test_closed_plan_returns_immutable_typed_plan(resource_plan):
    outcome = validate_resource_plan_structure(resource_plan)

    assert outcome.valid is True
    assert outcome.plan is not None
    assert outcome.plan.tasks[0].task_id == "run_experiment"
    with pytest.raises(AttributeError):
        outcome.plan.readiness = "needs_input"


@pytest.mark.parametrize(
    ("mutation", "code", "path"),
    [
        (lambda plan: plan["tasks"][0].update(depends_on=["run_experiment"]), "self_dependency", "tasks[0].depends_on[0]"),
        (
            lambda plan: plan["tasks"].append(
                {
                    **plan["tasks"][0],
                    "task_id": "prepare_inputs",
                    "kind": "preparation",
                    "depends_on": ["run_experiment"],
                }
            ) or plan["tasks"][0].update(depends_on=["prepare_inputs"]),
            "cyclic_dependency",
            "tasks",
        ),
        (lambda plan: plan["budget"].update(peak_memory_bytes=2), "aggregate_mismatch", "budget.peak_memory_bytes"),
    ],
)
def test_closed_plan_rejects_cycles_and_incorrect_aggregate(resource_plan, mutation, code, path):
    plan = copy.deepcopy(resource_plan)
    mutation(plan)

    issues = validate_resource_plan_structure(plan).issues

    assert any(issue.code == code and issue.path == path for issue in issues)


def test_closed_plan_requires_a_preparation_task_when_inputs_are_declared(resource_plan):
    resource_plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": False,
            "is_regular_file": False,
            "size_bytes": 0,
            "sha256": None,
            "license_status": "unconfirmed",
            "preparation_note": "Place the licensed input at data/input.csv.",
        }
    ]

    issues = validate_resource_plan_structure(resource_plan).issues

    assert "missing_preparation_task" in {issue.code for issue in issues}


def test_closed_plan_rejects_duplicate_input_paths_and_boolean_resource_quantities(resource_plan):
    resource_plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": False,
            "is_regular_file": False,
            "size_bytes": 0,
            "sha256": None,
            "license_status": "unconfirmed",
            "preparation_note": "Place the licensed input at data/input.csv.",
        },
        {
            "path": "data/input.csv",
            "required": True,
            "exists": False,
            "is_regular_file": False,
            "size_bytes": 0,
            "sha256": None,
            "license_status": "unconfirmed",
            "preparation_note": "Place the licensed input at data/input.csv.",
        },
    ]
    resource_plan["tasks"].append(
        {
            **resource_plan["tasks"][0],
            "task_id": "prepare_inputs",
            "kind": "preparation",
            "cpu_count": True,
        }
    )

    issues = validate_resource_plan_structure(resource_plan).issues

    assert any(issue.code == "duplicate_input_path" and issue.path == "inputs[1].path" for issue in issues)
    assert any(issue.code == "invalid_type" and issue.path == "tasks[1].cpu_count" for issue in issues)


@pytest.mark.parametrize(
    ("path", "mutation"),
    [
        ("hardware_observation.extra", lambda plan: plan["hardware_observation"].update(extra=True)),
        ("bindings.design.extra", lambda plan: plan["bindings"].update(design={"path": "experiment/design.json", "sha256": "a", "extra": True})),
        ("readiness", lambda plan: plan.update(readiness="invalid_plan")),
    ],
)
def test_closed_plan_rejects_unknown_nested_fields_and_invalid_readiness(resource_plan, path, mutation):
    mutation(resource_plan)

    issues = validate_resource_plan_structure(resource_plan).issues

    assert any(issue.path == path for issue in issues)


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("deferred_command", "python other.py", "invalid_command"),
        ("result_path", "experiment/other.json", "invalid_result_path"),
    ],
)
def test_closed_plan_rejects_deferred_command_and_result_path_drift(resource_plan, key, value, code):
    resource_plan[key] = value

    assert code in {issue.code for issue in validate_resource_plan_structure(resource_plan).issues}


@pytest.mark.parametrize("prohibition", ["network_access", "downloads", "package_installation", "external_llm_calls", "nested_agent_processes", "generated_code_execution"])
def test_closed_plan_rejects_prohibition_drift(resource_plan, prohibition):
    resource_plan["prohibitions"][prohibition] = True

    assert "prohibition_mismatch" in {
        issue.code for issue in validate_resource_plan_structure(resource_plan).issues
    }


def test_ready_plan_advances_to_locked_stage_twelve(stage_11_project, ready_plan):
    _write_json(stage_11_project.root / "experiment/resources.json", ready_plan)

    report = validate_current_stage(stage_11_project)
    state = ResearchProject.open(stage_11_project.root).state

    assert report.valid is True
    assert state.current_stage == 12
    assert state.completed_stages[-1] == 11
    assert state.status is StageStatus.AWAITING_APPROVAL
    assert state.next_action == "approve_experiment_execution"
    assert not (stage_11_project.root / "experiment/results.json").exists()


def test_truthful_missing_input_completes_planning_but_locks_approval(
    stage_11_project, missing_plan
):
    _write_json(stage_11_project.root / "experiment/resources.json", missing_plan)

    assert validate_current_stage(stage_11_project).valid is True
    state = ResearchProject.open(stage_11_project.root).state

    assert state.current_stage == 12
    assert state.status is StageStatus.AWAITING_APPROVAL
    assert state.next_action == "report_missing_execution_inputs"


@pytest.mark.parametrize(
    ("binding", "code"),
    [
        ("design", "binding_hash_mismatch"),
        ("package_manifest", "binding_hash_mismatch"),
        ("config", "binding_hash_mismatch"),
    ],
)
def test_stage_eleven_rejects_stale_code_package_bindings(
    stage_11_project, ready_plan, binding, code
):
    ready_plan["bindings"][binding]["sha256"] = "0" * 64

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert code in {issue.code for issue in issues}


@pytest.mark.parametrize("unsafe_path", ["../outside.csv", "data/../outside.csv"])
def test_stage_eleven_rejects_input_path_traversal(
    stage_11_project, missing_plan, unsafe_path
):
    missing_plan["inputs"][0]["path"] = unsafe_path

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert "unsafe_input_path" in {issue.code for issue in issues}


def test_stage_eleven_rejects_input_symlink_components(
    stage_11_project, missing_plan, tmp_path
):
    outside = tmp_path / "outside"
    outside.mkdir()
    (stage_11_project.root / "data").symlink_to(outside, target_is_directory=True)

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert "unsafe_input_path" in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("exists", False, "input_fact_mismatch"),
        ("is_regular_file", False, "input_fact_mismatch"),
        ("size_bytes", 0, "input_fact_mismatch"),
        ("sha256", "0" * 64, "input_fact_mismatch"),
    ],
)
def test_stage_eleven_rejects_false_input_filesystem_facts(
    stage_11_project, ready_plan, field, value, code
):
    input_path = stage_11_project.root / "data/input.csv"
    input_path.parent.mkdir()
    input_path.write_text("value\n1\n", encoding="utf-8")
    ready_plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": True,
            "is_regular_file": True,
            "size_bytes": input_path.stat().st_size,
            "sha256": _sha256(input_path),
            "license_status": "confirmed",
            "preparation_note": "Verify data/input.csv before execution.",
        }
    ]
    ready_plan["tasks"].insert(
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
    ready_plan["tasks"][1]["depends_on"] = ["prepare_inputs"]
    ready_plan["budget"]["total_estimated_duration_seconds"] = 2
    ready_plan["inputs"][0][field] = value

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert code in {issue.code for issue in issues}


def test_stage_eleven_requires_closed_license_status(stage_11_project, missing_plan):
    missing_plan["inputs"][0]["license_status"] = "unknown"

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert "invalid_license_status" in {issue.code for issue in issues}


def test_stage_eleven_rejects_missing_license_status(stage_11_project, missing_plan):
    del missing_plan["inputs"][0]["license_status"]

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert any(
        issue.code == "missing_field" and issue.path == "inputs[0].license_status"
        for issue in issues
    )


@pytest.mark.parametrize(
    ("budget_field", "observation_field", "value"),
    [
        ("peak_cpu_count", "logical_cpu_count", 1),
        ("peak_memory_bytes", "total_memory_bytes", 1),
        ("peak_temporary_disk_bytes", "free_disk_bytes", 1),
        ("peak_gpu_count", "gpu_available", False),
    ],
)
def test_stage_eleven_requires_truthful_hardware_prerequisites(
    stage_11_project,
    ready_plan,
    budget_field,
    observation_field,
    value,
):
    ready_plan["hardware_observation"][observation_field] = value
    required = 2 if budget_field != "peak_gpu_count" else 1
    ready_plan["tasks"][0][
        {
            "peak_cpu_count": "cpu_count",
            "peak_memory_bytes": "memory_bytes",
            "peak_temporary_disk_bytes": "temporary_disk_bytes",
            "peak_gpu_count": "gpu_count",
        }[budget_field]
    ] = required
    ready_plan["budget"][budget_field] = required

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert "readiness_mismatch" in {issue.code for issue in issues}


def test_stage_eleven_rejects_preexisting_results(stage_11_project, ready_plan):
    (stage_11_project.root / "experiment/results.json").write_text(
        "{}\n", encoding="utf-8"
    )

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert "preexisting_result" in {issue.code for issue in issues}


@pytest.mark.parametrize(
    "unmet",
    [
        ["Provide the licensed input at data/input.csv.", "Provide the licensed input at data/input.csv."],
        ["Z action.", "A action."],
        ["Observe that input is absent."],
    ],
)
def test_stage_eleven_rejects_nondeterministic_or_non_actionable_prerequisites(
    stage_11_project, missing_plan, unmet
):
    missing_plan["unmet_prerequisites"] = unmet

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert "unmet_prerequisites_mismatch" in {issue.code for issue in issues}


def test_stage_eleven_rejects_saved_hardware_profile_drift(
    stage_11_project, ready_plan
):
    ready_plan["saved_hardware_profile"] = {"cpu": "different"}

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert "saved_profile_mismatch" in {issue.code for issue in issues}
