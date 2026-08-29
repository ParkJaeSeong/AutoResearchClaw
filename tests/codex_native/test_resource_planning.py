import copy

import pytest

from researchclaw.core.project import ResearchProject
from researchclaw.core.resource_planning import (
    HardwareObservation,
    observe_local_hardware,
    validate_resource_plan_structure,
)
from tests.codex_native.helpers import valid_resource_plan


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
