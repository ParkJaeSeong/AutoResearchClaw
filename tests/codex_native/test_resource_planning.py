import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from researchclaw.core.models import ArtifactRef, StageStatus
from researchclaw.core.project import ResearchProject
from researchclaw.core.resource_planning import (
    HardwareObservation,
    hardware_drift_warnings,
    observe_local_hardware,
    validate_stage_eleven,
    validate_resource_plan_structure,
)
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import (
    build_completed_validation_design_project,
    set_stage_ten_required_paths,
    valid_resource_plan,
    write_valid_fixture_artifacts,
)


_BINDING_PATHS = {
    "design": "experiment/design.json",
    "package_manifest": "experiment/package_manifest.json",
    "config": "experiment/code/config.json",
    "hardware_profile": "scope/hardware_profile.json",
}
_MISSING_INPUT_PREREQUISITES = [
    "Confirm license authorization for required input data/input.csv.",
    "Provide required input file at data/input.csv.",
]


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
    plan["warnings"] = list(
        hardware_drift_warnings(
            plan["saved_hardware_profile"],
            plan["hardware_observation"],
        )
    )
    config = json.loads(
        (project.root / "experiment/code/config.json").read_text(encoding="utf-8")
    )
    plan["inputs"] = [
        _input_fact(project, path, required=True)
        for path in config["input_contract"]["required_paths"]
    ]
    if plan["inputs"]:
        _add_preparation_task(plan)
    return plan


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _input_fact(project, relative_path, *, required):
    path = project.root / relative_path
    payload = path.read_bytes()
    return {
        "path": relative_path,
        "required": required,
        "exists": True,
        "is_regular_file": True,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "license_status": "confirmed",
        "preparation_note": f"Verify {relative_path} before execution.",
    }


def _add_preparation_task(plan):
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


@pytest.fixture
def stage_11_project(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    set_stage_ten_required_paths(project.root, ["data/input.csv"])
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    data_path = project.root / "data/input.csv"
    data_path.parent.mkdir(parents=True)
    data_path.write_text("value\n1\n", encoding="utf-8")
    return ResearchProject.open(project.root)


@pytest.fixture
def ready_plan(stage_11_project):
    return _semantic_plan(stage_11_project)


@pytest.fixture
def missing_plan(stage_11_project):
    plan = _semantic_plan(stage_11_project, readiness="needs_input")
    input_path = stage_11_project.root / "data/input.csv"
    input_path.unlink()
    input_path.parent.rmdir()
    plan["inputs"][0].update(
        {
            "exists": False,
            "is_regular_file": False,
            "size_bytes": 0,
            "sha256": None,
            "license_status": "unconfirmed",
            "preparation_note": "Provide the licensed input at data/input.csv.",
        }
    )
    plan["unmet_prerequisites"] = list(_MISSING_INPUT_PREREQUISITES)
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


def test_stage_eleven_rejects_omitted_config_required_path(
    stage_11_project,
    ready_plan,
):
    ready_plan["inputs"] = []

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert any(
        issue.code == "required_input_set_mismatch" and issue.path == "inputs"
        for issue in issues
    )


def test_stage_eleven_rejects_config_required_path_marked_optional(
    stage_11_project,
    ready_plan,
):
    ready_plan["inputs"] = [
        _input_fact(stage_11_project, "data/input.csv", required=False)
    ]

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert any(
        issue.code == "required_input_flag_mismatch"
        and issue.path == "inputs[0].required"
        for issue in issues
    )


def test_stage_eleven_rejects_required_input_set_mismatch(
    stage_11_project,
    ready_plan,
):
    ready_plan["inputs"] = [
        _input_fact(stage_11_project, "scope/goal.md", required=True)
    ]

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert any(
        issue.code == "required_input_set_mismatch" and issue.path == "inputs"
        for issue in issues
    )


def test_stage_eleven_accepts_validated_optional_input_extras(
    stage_11_project,
    ready_plan,
):
    ready_plan["inputs"].append(
        _input_fact(stage_11_project, "scope/goal.md", required=False)
    )

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert issues == ()


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
    monkeypatch,
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
    current = HardwareObservation(**ready_plan["hardware_observation"])
    monkeypatch.setattr(
        "researchclaw.core.resource_planning.observe_local_hardware",
        lambda _root: current,
    )

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


def test_stage_eleven_never_trusts_plan_authored_gpu_availability(
    stage_11_project, ready_plan
):
    ready_plan["hardware_observation"]["gpu_available"] = True
    ready_plan["tasks"][0]["gpu_count"] = 1
    ready_plan["budget"]["peak_gpu_count"] = 1

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)
    codes = {issue.code for issue in issues}

    assert "hardware_observation_mismatch" in codes
    assert "readiness_mismatch" in codes


def test_stage_eleven_records_unknown_single_gpu_as_unmet(
    stage_11_project, ready_plan
):
    ready_plan["tasks"][0]["gpu_count"] = 1
    ready_plan["budget"]["peak_gpu_count"] = 1
    ready_plan["readiness"] = "needs_input"
    ready_plan["unmet_prerequisites"] = ["Provide at least 1 available GPU."]

    _plan, issues = validate_stage_eleven(stage_11_project, ready_plan)

    assert issues == ()


def test_closed_plan_rejects_gpu_counts_the_passive_boolean_cannot_prove(
    resource_plan,
):
    resource_plan["tasks"][0]["gpu_count"] = 2
    resource_plan["budget"]["peak_gpu_count"] = 2

    issues = validate_resource_plan_structure(resource_plan).issues

    assert any(
        issue.code == "unsupported_gpu_count"
        and issue.path == "budget.peak_gpu_count"
        for issue in issues
    )


def test_stage_eleven_rejects_author_controlled_generic_missing_input_message(
    stage_11_project, missing_plan
):
    missing_plan["inputs"][0]["preparation_note"] = "Input is absent."
    missing_plan["unmet_prerequisites"] = ["Input is absent."]

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert "unmet_prerequisites_mismatch" in {issue.code for issue in issues}


def test_stage_eleven_accepts_engine_derived_missing_input_actions(
    stage_11_project, missing_plan
):
    missing_plan["inputs"][0]["preparation_note"] = "Input is absent."

    _plan, issues = validate_stage_eleven(stage_11_project, missing_plan)

    assert issues == ()


def test_stage_eleven_compares_saved_profile_arrays_by_json_value(
    stage_11_project, ready_plan
):
    profile = {
        "cpu": "apple",
        "memory_gb": 128,
        "storage": ["internal", ["encrypted", "apfs"]],
    }
    profile_path = stage_11_project.root / "scope/hardware_profile.json"
    payload = (json.dumps(profile, sort_keys=True) + "\n").encode("utf-8")
    profile_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    state = stage_11_project.state
    updated = stage_11_project.persist_state(
        replace(
            state,
            artifacts={
                **state.artifacts,
                "scope/hardware_profile.json": ArtifactRef(
                    path="scope/hardware_profile.json",
                    sha256=digest,
                    size=len(payload),
                ),
            },
        )
    )
    ready_plan["bindings"]["hardware_profile"]["sha256"] = digest
    ready_plan["saved_hardware_profile"] = profile

    _plan, issues = validate_stage_eleven(updated, ready_plan)

    assert "saved_profile_mismatch" not in {issue.code for issue in issues}


def test_stage_eleven_generates_real_drift_warnings_for_legacy_hardware_aliases(
    stage_11_project,
    ready_plan,
):
    observed = HardwareObservation(**ready_plan["hardware_observation"])
    saved_cpu = observed.logical_cpu_count + 1
    saved_memory_gb = 0 if observed.total_memory_bytes else 1
    mapped_memory_bytes = saved_memory_gb * 1_073_741_824
    profile = {
        "cpu": saved_cpu,
        "memory_gb": saved_memory_gb,
        "machine_label": "preserved evidence",
    }
    profile_path = stage_11_project.root / "scope/hardware_profile.json"
    payload = (json.dumps(profile, sort_keys=True) + "\n").encode("utf-8")
    profile_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    state = stage_11_project.state
    updated = stage_11_project.persist_state(
        replace(
            state,
            artifacts={
                **state.artifacts,
                "scope/hardware_profile.json": ArtifactRef(
                    path="scope/hardware_profile.json",
                    sha256=digest,
                    size=len(payload),
                ),
            },
        )
    )
    ready_plan["bindings"]["hardware_profile"]["sha256"] = digest
    ready_plan["saved_hardware_profile"] = profile
    ready_plan["warnings"] = sorted(
        [
            (
                "Saved hardware profile field 'cpu' (logical_cpu_count) differs "
                f"from the passive observation: {saved_cpu} != "
                f"{observed.logical_cpu_count}."
            ),
            (
                "Saved hardware profile field 'memory_gb' (total_memory_bytes via "
                "1073741824 bytes/GiB) differs from the passive observation: "
                f"{mapped_memory_bytes} != {observed.total_memory_bytes}."
            ),
        ]
    )
    before = profile_path.read_bytes()

    _plan, issues = validate_stage_eleven(updated, ready_plan)

    assert issues == ()
    assert profile_path.read_bytes() == before


def test_legacy_memory_alias_maps_arbitrary_non_negative_json_integers():
    saved_profile = {"memory_gb": 10**400, "machine_label": "preserved evidence"}
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

    warnings = hardware_drift_warnings(saved_profile, observation)

    assert len(warnings) == 1
    assert "'memory_gb' (total_memory_bytes via 1073741824 bytes/GiB)" in warnings[0]
    assert saved_profile["machine_label"] == "preserved evidence"
