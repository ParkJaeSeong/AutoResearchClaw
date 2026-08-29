"""Passive local hardware facts used by Stage 11 resource planning."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import stat
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

from .paths import resolve_project_artifact

if TYPE_CHECKING:
    from .project import ResearchProject
    from .validation import ValidationIssue


RESOURCE_PLAN_SCHEMA_VERSION = 1
DEFERRED_EXPERIMENT_COMMAND = "python experiment/code/main.py --config experiment/code/config.json"
EXPERIMENT_RESULT_PATH = "experiment/results.json"
RESOURCE_PLAN_PATH = "experiment/resources.json"
RESOURCE_PLAN_PROHIBITIONS = MappingProxyType(
    {
        "network_access": False,
        "downloads": False,
        "package_installation": False,
        "external_llm_calls": False,
        "nested_agent_processes": False,
        "generated_code_execution": False,
    }
)

_ROOT_FIELDS = {
    "schema_version",
    "project_id",
    "bindings",
    "saved_hardware_profile",
    "hardware_observation",
    "inputs",
    "tasks",
    "budget",
    "deferred_command",
    "result_path",
    "prohibitions",
    "warnings",
    "unmet_prerequisites",
    "readiness",
}
_BINDING_FIELDS = {"path", "sha256"}
_OBSERVATION_FIELDS = {
    "logical_cpu_count",
    "total_memory_bytes",
    "free_disk_bytes",
    "platform",
    "architecture",
    "gpu_available",
    "method",
    "observed_at",
}
_INPUT_FIELDS = {
    "path",
    "required",
    "exists",
    "is_regular_file",
    "size_bytes",
    "sha256",
    "license_status",
    "preparation_note",
}
_TASK_FIELDS = {
    "task_id",
    "kind",
    "depends_on",
    "priority",
    "cpu_count",
    "memory_bytes",
    "gpu_count",
    "temporary_disk_bytes",
    "estimated_duration_seconds",
}
_BUDGET_FIELDS = {
    "max_parallel_tasks",
    "peak_cpu_count",
    "peak_memory_bytes",
    "peak_gpu_count",
    "peak_temporary_disk_bytes",
    "total_estimated_duration_seconds",
}
_PREPARATION_KINDS = frozenset({"preparation", "readiness"})
_READINESS_VALUES = frozenset({"ready_for_execution", "needs_input"})
_LICENSE_VALUES = frozenset({"confirmed", "not_required", "unconfirmed"})
_HASH_CHUNK_SIZE = 1024 * 1024
_FREE_DISK_SNAPSHOT_TOLERANCE = 16 * 1024 * 1024
_BYTES_PER_GIB = 1_073_741_824
_REQUIRED_BINDINGS = MappingProxyType(
    {
        "design": "experiment/design.json",
        "package_manifest": "experiment/package_manifest.json",
        "config": "experiment/code/config.json",
        "hardware_profile": "scope/hardware_profile.json",
    }
)


@dataclass(frozen=True)
class HardwareObservation:
    logical_cpu_count: int
    total_memory_bytes: int
    free_disk_bytes: int
    platform: str
    architecture: str
    gpu_available: bool | None
    method: str
    observed_at: str

    def to_dict(self) -> dict[str, object]:
        """Serialize this immutable observation for a durable task packet."""
        return asdict(self)


@dataclass(frozen=True)
class ResourcePlanIssue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class ResourceBinding:
    name: str
    path: str
    sha256: str


@dataclass(frozen=True)
class InputReadiness:
    path: str
    required: bool
    exists: bool
    is_regular_file: bool
    size_bytes: int
    sha256: str | None
    license_status: str
    preparation_note: str


@dataclass(frozen=True)
class ResourceTask:
    task_id: str
    kind: str
    depends_on: tuple[str, ...]
    priority: int
    cpu_count: int
    memory_bytes: int
    gpu_count: int
    temporary_disk_bytes: int
    estimated_duration_seconds: int


@dataclass(frozen=True)
class ResourceBudget:
    max_parallel_tasks: int
    peak_cpu_count: int
    peak_memory_bytes: int
    peak_gpu_count: int
    peak_temporary_disk_bytes: int
    total_estimated_duration_seconds: int


@dataclass(frozen=True)
class ResourcePlan:
    schema_version: int
    project_id: str
    bindings: tuple[ResourceBinding, ...]
    saved_hardware_profile: Mapping[str, object]
    hardware_observation: HardwareObservation
    inputs: tuple[InputReadiness, ...]
    tasks: tuple[ResourceTask, ...]
    budget: ResourceBudget
    deferred_command: str
    result_path: str
    prohibitions: Mapping[str, bool]
    warnings: tuple[str, ...]
    unmet_prerequisites: tuple[str, ...]
    readiness: str


@dataclass(frozen=True)
class ResourcePlanOutcome:
    plan: ResourcePlan | None
    issues: tuple[ResourcePlanIssue, ...]

    @property
    def valid(self) -> bool:
        return self.plan is not None and not self.issues


def _total_memory_bytes() -> int:
    """Return the physical-memory fact available through the Python standard library."""
    try:
        return max(0, os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def observe_local_hardware(root: Path) -> HardwareObservation:
    """Observe local hardware without subprocesses, probes, or generated-code execution."""
    return HardwareObservation(
        logical_cpu_count=max(1, os.cpu_count() or 1),
        total_memory_bytes=_total_memory_bytes(),
        free_disk_bytes=shutil.disk_usage(root).free,
        platform=platform.system(),
        architecture=platform.machine(),
        gpu_available=None,
        method="python_stdlib_passive",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )


def _issue(issues: list[ResourcePlanIssue], code: str, path: str, message: str) -> None:
    issues.append(ResourcePlanIssue(code, path, message))


def _closed_object(
    raw: object,
    required_fields: set[str] | frozenset[str],
    path: str,
    issues: list[ResourcePlanIssue],
) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        _issue(issues, "invalid_type", path, "must be a JSON object")
        return None
    for field in sorted(required_fields - raw.keys()):
        _issue(issues, "missing_field", f"{path}.{field}" if path else field, "required field is missing")
    for field in sorted(raw.keys() - required_fields):
        _issue(issues, "unknown_field", f"{path}.{field}" if path else field, "field is not allowed")
    return raw


def _non_negative_integer(
    value: object,
    path: str,
    issues: list[ResourcePlanIssue],
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        _issue(issues, "invalid_type", path, "must be an integer")
        return None
    if value < 0:
        _issue(issues, "invalid_resource_value", path, "must not be negative")
        return None
    return value


def _string(value: object, path: str, issues: list[ResourcePlanIssue]) -> str | None:
    if not isinstance(value, str):
        _issue(issues, "invalid_type", path, "must be a string")
        return None
    if not value:
        _issue(issues, "invalid_value", path, "must not be empty")
        return None
    return value


def _boolean(value: object, path: str, issues: list[ResourcePlanIssue]) -> bool | None:
    if not isinstance(value, bool):
        _issue(issues, "invalid_type", path, "must be a boolean")
        return None
    return value


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _parse_observation(
    raw: object, path: str, issues: list[ResourcePlanIssue]
) -> HardwareObservation | None:
    value = _closed_object(raw, _OBSERVATION_FIELDS, path, issues)
    if value is None:
        return None
    logical_cpu_count = _non_negative_integer(value.get("logical_cpu_count"), f"{path}.logical_cpu_count", issues)
    total_memory_bytes = _non_negative_integer(value.get("total_memory_bytes"), f"{path}.total_memory_bytes", issues)
    free_disk_bytes = _non_negative_integer(value.get("free_disk_bytes"), f"{path}.free_disk_bytes", issues)
    platform_name = _string(value.get("platform"), f"{path}.platform", issues)
    architecture = _string(value.get("architecture"), f"{path}.architecture", issues)
    gpu_available = value.get("gpu_available")
    if gpu_available is not None and not isinstance(gpu_available, bool):
        _issue(issues, "invalid_type", f"{path}.gpu_available", "must be a boolean or null")
        gpu_available = None
    method = _string(value.get("method"), f"{path}.method", issues)
    observed_at = _string(value.get("observed_at"), f"{path}.observed_at", issues)
    if None in (
        logical_cpu_count,
        total_memory_bytes,
        free_disk_bytes,
        platform_name,
        architecture,
        method,
        observed_at,
    ):
        return None
    return HardwareObservation(
        logical_cpu_count=logical_cpu_count,
        total_memory_bytes=total_memory_bytes,
        free_disk_bytes=free_disk_bytes,
        platform=platform_name,
        architecture=architecture,
        gpu_available=gpu_available,
        method=method,
        observed_at=observed_at,
    )


def _parse_bindings(raw: object, issues: list[ResourcePlanIssue]) -> tuple[ResourceBinding, ...] | None:
    if not isinstance(raw, dict):
        _issue(issues, "invalid_type", "bindings", "must be a JSON object")
        return None
    bindings: list[ResourceBinding] = []
    for name, raw_binding in raw.items():
        if not isinstance(name, str) or not name:
            _issue(issues, "invalid_value", "bindings", "binding names must be non-empty strings")
            continue
        path = f"bindings.{name}"
        binding = _closed_object(raw_binding, _BINDING_FIELDS, path, issues)
        if binding is None:
            continue
        bound_path = _string(binding.get("path"), f"{path}.path", issues)
        sha256 = _string(binding.get("sha256"), f"{path}.sha256", issues)
        if bound_path is not None and sha256 is not None:
            bindings.append(ResourceBinding(name=name, path=bound_path, sha256=sha256))
    return tuple(bindings)


def _parse_inputs(raw: object, issues: list[ResourcePlanIssue]) -> tuple[InputReadiness, ...] | None:
    if not isinstance(raw, list):
        _issue(issues, "invalid_type", "inputs", "must be a JSON array")
        return None
    inputs: list[InputReadiness] = []
    paths: set[str] = set()
    for index, raw_input in enumerate(raw):
        path = f"inputs[{index}]"
        value = _closed_object(raw_input, _INPUT_FIELDS, path, issues)
        if value is None:
            continue
        input_path = _string(value.get("path"), f"{path}.path", issues)
        required = _boolean(value.get("required"), f"{path}.required", issues)
        exists = _boolean(value.get("exists"), f"{path}.exists", issues)
        is_regular_file = _boolean(value.get("is_regular_file"), f"{path}.is_regular_file", issues)
        size_bytes = _non_negative_integer(value.get("size_bytes"), f"{path}.size_bytes", issues)
        sha256 = value.get("sha256")
        if sha256 is not None and not isinstance(sha256, str):
            _issue(issues, "invalid_type", f"{path}.sha256", "must be a string or null")
            sha256 = None
        license_status = _string(value.get("license_status"), f"{path}.license_status", issues)
        preparation_note = _string(value.get("preparation_note"), f"{path}.preparation_note", issues)
        if input_path is not None:
            if input_path in paths:
                _issue(issues, "duplicate_input_path", f"{path}.path", "input path is declared more than once")
            paths.add(input_path)
        if None not in (
            input_path,
            required,
            exists,
            is_regular_file,
            size_bytes,
            license_status,
            preparation_note,
        ):
            inputs.append(
                InputReadiness(
                    path=input_path,
                    required=required,
                    exists=exists,
                    is_regular_file=is_regular_file,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    license_status=license_status,
                    preparation_note=preparation_note,
                )
            )
    return tuple(inputs)


def _parse_tasks(raw: object, issues: list[ResourcePlanIssue]) -> tuple[ResourceTask, ...] | None:
    if not isinstance(raw, list):
        _issue(issues, "invalid_type", "tasks", "must be a JSON array")
        return None
    tasks: list[ResourceTask] = []
    task_ids: set[str] = set()
    for index, raw_task in enumerate(raw):
        path = f"tasks[{index}]"
        value = _closed_object(raw_task, _TASK_FIELDS, path, issues)
        if value is None:
            continue
        task_id = _string(value.get("task_id"), f"{path}.task_id", issues)
        kind = _string(value.get("kind"), f"{path}.kind", issues)
        raw_dependencies = value.get("depends_on")
        dependencies: list[str] = []
        if not isinstance(raw_dependencies, list):
            _issue(issues, "invalid_type", f"{path}.depends_on", "must be a JSON array")
        else:
            for dependency_index, dependency in enumerate(raw_dependencies):
                parsed_dependency = _string(
                    dependency, f"{path}.depends_on[{dependency_index}]", issues
                )
                if parsed_dependency is not None:
                    dependencies.append(parsed_dependency)
        priority = _non_negative_integer(value.get("priority"), f"{path}.priority", issues)
        cpu_count = _non_negative_integer(value.get("cpu_count"), f"{path}.cpu_count", issues)
        memory_bytes = _non_negative_integer(value.get("memory_bytes"), f"{path}.memory_bytes", issues)
        gpu_count = _non_negative_integer(value.get("gpu_count"), f"{path}.gpu_count", issues)
        temporary_disk_bytes = _non_negative_integer(
            value.get("temporary_disk_bytes"), f"{path}.temporary_disk_bytes", issues
        )
        estimated_duration_seconds = _non_negative_integer(
            value.get("estimated_duration_seconds"), f"{path}.estimated_duration_seconds", issues
        )
        if task_id is not None:
            if task_id in task_ids:
                _issue(issues, "duplicate_task_id", f"{path}.task_id", "task ID is declared more than once")
            task_ids.add(task_id)
        if None not in (
            task_id,
            kind,
            priority,
            cpu_count,
            memory_bytes,
            gpu_count,
            temporary_disk_bytes,
            estimated_duration_seconds,
        ) and isinstance(raw_dependencies, list):
            tasks.append(
                ResourceTask(
                    task_id=task_id,
                    kind=kind,
                    depends_on=tuple(dependencies),
                    priority=priority,
                    cpu_count=cpu_count,
                    memory_bytes=memory_bytes,
                    gpu_count=gpu_count,
                    temporary_disk_bytes=temporary_disk_bytes,
                    estimated_duration_seconds=estimated_duration_seconds,
                )
            )
    return tuple(tasks)


def _parse_budget(raw: object, issues: list[ResourcePlanIssue]) -> ResourceBudget | None:
    value = _closed_object(raw, _BUDGET_FIELDS, "budget", issues)
    if value is None:
        return None
    parsed = {
        field: _non_negative_integer(value.get(field), f"budget.{field}", issues)
        for field in _BUDGET_FIELDS
    }
    if any(item is None for item in parsed.values()):
        return None
    return ResourceBudget(**parsed)  # type: ignore[arg-type]


def _validate_dag(tasks: tuple[ResourceTask, ...], issues: list[ResourcePlanIssue]) -> None:
    task_ids = {task.task_id for task in tasks}
    dependencies = {task.task_id: task.depends_on for task in tasks}
    for index, task in enumerate(tasks):
        for dependency_index, dependency in enumerate(task.depends_on):
            path = f"tasks[{index}].depends_on[{dependency_index}]"
            if dependency == task.task_id:
                _issue(issues, "self_dependency", path, "a task cannot depend on itself")
            elif dependency not in task_ids:
                _issue(issues, "missing_dependency", path, "dependency does not name a task")

    colors = {task_id: 0 for task_id in task_ids}
    for root in sorted(task_ids):
        if colors[root]:
            continue
        colors[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            task_id, dependency_index = stack[-1]
            task_dependencies = dependencies[task_id]
            if dependency_index == len(task_dependencies):
                colors[task_id] = 2
                stack.pop()
                continue
            dependency = task_dependencies[dependency_index]
            stack[-1] = (task_id, dependency_index + 1)
            if dependency not in colors:
                continue
            if colors[dependency] == 1:
                _issue(issues, "cyclic_dependency", "tasks", "task dependencies must be acyclic")
                return
            if colors[dependency] == 0:
                colors[dependency] = 1
                stack.append((dependency, 0))


def _validate_budget(
    tasks: tuple[ResourceTask, ...], budget: ResourceBudget, issues: list[ResourcePlanIssue]
) -> None:
    if budget.max_parallel_tasks != 1:
        _issue(
            issues,
            "unsupported_parallelism",
            "budget.max_parallel_tasks",
            "max_parallel_tasks must be exactly 1",
        )
    if budget.peak_gpu_count > 1:
        _issue(
            issues,
            "unsupported_gpu_count",
            "budget.peak_gpu_count",
            "passive GPU availability can support at most one declared GPU",
        )
    if not tasks:
        return
    expected_budget = {
        "max_parallel_tasks": 1,
        "peak_cpu_count": max(task.cpu_count for task in tasks),
        "peak_memory_bytes": max(task.memory_bytes for task in tasks),
        "peak_gpu_count": max(task.gpu_count for task in tasks),
        "peak_temporary_disk_bytes": max(task.temporary_disk_bytes for task in tasks),
        "total_estimated_duration_seconds": sum(
            task.estimated_duration_seconds for task in tasks
        ),
    }
    for field, expected in expected_budget.items():
        if getattr(budget, field) != expected:
            _issue(
                issues,
                "aggregate_mismatch",
                f"budget.{field}",
                "budget value does not match the declared tasks",
            )


def _parse_string_list(
    raw: object, path: str, issues: list[ResourcePlanIssue]
) -> tuple[str, ...] | None:
    if not isinstance(raw, list):
        _issue(issues, "invalid_type", path, "must be a JSON array")
        return None
    values: list[str] = []
    for index, value in enumerate(raw):
        parsed = _string(value, f"{path}[{index}]", issues)
        if parsed is not None:
            values.append(parsed)
    return tuple(values)


def validate_resource_plan_structure(raw: object) -> ResourcePlanOutcome:
    """Parse the closed Stage-11 plan schema without reading project state."""
    issues: list[ResourcePlanIssue] = []
    value = _closed_object(raw, _ROOT_FIELDS, "", issues)
    if value is None:
        return ResourcePlanOutcome(plan=None, issues=tuple(issues))

    schema_version = _non_negative_integer(value.get("schema_version"), "schema_version", issues)
    if schema_version is not None and schema_version != RESOURCE_PLAN_SCHEMA_VERSION:
        _issue(issues, "unsupported_schema_version", "schema_version", "must be exactly 1")
    project_id = _string(value.get("project_id"), "project_id", issues)
    bindings = _parse_bindings(value.get("bindings"), issues)

    saved_hardware_profile = value.get("saved_hardware_profile")
    if not isinstance(saved_hardware_profile, dict):
        _issue(issues, "invalid_type", "saved_hardware_profile", "must be a JSON object")
        saved_hardware_profile = None
    hardware_observation = _parse_observation(value.get("hardware_observation"), "hardware_observation", issues)
    inputs = _parse_inputs(value.get("inputs"), issues)
    tasks = _parse_tasks(value.get("tasks"), issues)
    budget = _parse_budget(value.get("budget"), issues)
    deferred_command = _string(value.get("deferred_command"), "deferred_command", issues)
    if deferred_command is not None and deferred_command != DEFERRED_EXPERIMENT_COMMAND:
        _issue(issues, "invalid_command", "deferred_command", "must match the fixed deferred command")
    result_path = _string(value.get("result_path"), "result_path", issues)
    if result_path is not None and result_path != EXPERIMENT_RESULT_PATH:
        _issue(issues, "invalid_result_path", "result_path", "must match the fixed result path")

    prohibitions = _closed_object(value.get("prohibitions"), set(RESOURCE_PLAN_PROHIBITIONS), "prohibitions", issues)
    parsed_prohibitions: dict[str, bool] = {}
    if prohibitions is not None:
        for prohibition, expected in RESOURCE_PLAN_PROHIBITIONS.items():
            actual = _boolean(prohibitions.get(prohibition), f"prohibitions.{prohibition}", issues)
            if actual is not None:
                parsed_prohibitions[prohibition] = actual
                if actual != expected:
                    _issue(
                        issues,
                        "prohibition_mismatch",
                        f"prohibitions.{prohibition}",
                        "prohibition must remain false during resource planning",
                    )
    warnings = _parse_string_list(value.get("warnings"), "warnings", issues)
    unmet_prerequisites = _parse_string_list(
        value.get("unmet_prerequisites"), "unmet_prerequisites", issues
    )
    readiness = _string(value.get("readiness"), "readiness", issues)
    if readiness is not None and readiness not in _READINESS_VALUES:
        _issue(issues, "invalid_readiness", "readiness", "must be a supported readiness value")

    if tasks is not None:
        _validate_dag(tasks, issues)
        experiment_tasks = sum(task.kind == "experiment" for task in tasks)
        if experiment_tasks != 1:
            _issue(issues, "invalid_experiment_task_count", "tasks", "exactly one experiment task is required")
        if inputs and not any(task.kind in _PREPARATION_KINDS for task in tasks):
            _issue(
                issues,
                "missing_preparation_task",
                "tasks",
                "declared inputs require a preparation or readiness task",
            )
    if tasks is not None and budget is not None:
        _validate_budget(tasks, budget, issues)

    if issues or None in (
        schema_version,
        project_id,
        bindings,
        saved_hardware_profile,
        hardware_observation,
        inputs,
        tasks,
        budget,
        deferred_command,
        result_path,
        warnings,
        unmet_prerequisites,
        readiness,
    ):
        return ResourcePlanOutcome(plan=None, issues=tuple(issues))
    return ResourcePlanOutcome(
        plan=ResourcePlan(
            schema_version=schema_version,
            project_id=project_id,
            bindings=bindings,
            saved_hardware_profile=_freeze_json(deepcopy(saved_hardware_profile)),
            hardware_observation=hardware_observation,
            inputs=inputs,
            tasks=tasks,
            budget=budget,
            deferred_command=deferred_command,
            result_path=result_path,
            prohibitions=MappingProxyType(parsed_prohibitions),
            warnings=warnings,
            unmet_prerequisites=unmet_prerequisites,
            readiness=readiness,
        ),
        issues=tuple(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validation_issue(code: str, path: str, message: str) -> "ValidationIssue":
    from .validation import ValidationIssue

    return ValidationIssue(code=code, path=path, message=message)


def _as_validation_issue(issue: ResourcePlanIssue) -> "ValidationIssue":
    return _validation_issue(issue.code, issue.path, issue.message)


def hardware_drift_warnings(
    saved_profile: Mapping[str, object],
    observation: HardwareObservation | Mapping[str, object],
) -> tuple[str, ...]:
    """Derive drift warnings without rewriting canonical or legacy evidence."""
    observed = (
        observation.to_dict()
        if isinstance(observation, HardwareObservation)
        else observation
    )
    comparisons: list[tuple[str, str, object, object, str | None]] = []
    for field in (
        "logical_cpu_count",
        "total_memory_bytes",
        "free_disk_bytes",
        "platform",
        "architecture",
        "gpu_available",
    ):
        saved = saved_profile.get(field)
        if saved is not None:
            comparisons.append((field, field, saved, observed[field], None))

    if saved_profile.get("logical_cpu_count") is None:
        saved_cpu = saved_profile.get("cpu")
        if isinstance(saved_cpu, int) and not isinstance(saved_cpu, bool):
            comparisons.append(
                ("cpu", "logical_cpu_count", saved_cpu, observed["logical_cpu_count"], None)
            )
    if saved_profile.get("total_memory_bytes") is None:
        saved_memory_gb = saved_profile.get("memory_gb")
        if (
            isinstance(saved_memory_gb, (int, float))
            and not isinstance(saved_memory_gb, bool)
            and (
                isinstance(saved_memory_gb, int)
                or math.isfinite(saved_memory_gb)
            )
            and saved_memory_gb >= 0
        ):
            mapped_fraction = Fraction(str(saved_memory_gb)) * _BYTES_PER_GIB
            mapped_memory: int | float = (
                mapped_fraction.numerator
                if mapped_fraction.denominator == 1
                else float(mapped_fraction)
            )
            comparisons.append(
                (
                    "memory_gb",
                    "total_memory_bytes",
                    mapped_memory,
                    observed["total_memory_bytes"],
                    f"total_memory_bytes via {_BYTES_PER_GIB} bytes/GiB",
                )
            )

    warnings: set[str] = set()
    for saved_field, observed_field, saved, current, alias_label in comparisons:
        if saved == current:
            continue
        field_label = (
            f"{saved_field!r} ({alias_label or observed_field})"
            if saved_field != observed_field
            else repr(saved_field)
        )
        warnings.add(
            f"Saved hardware profile field {field_label} differs from the passive "
            f"observation: {json.dumps(saved, sort_keys=True)} != "
            f"{json.dumps(current, sort_keys=True)}."
        )
    return tuple(sorted(warnings))


def _hardware_drift_warnings(plan: ResourcePlan) -> tuple[str, ...]:
    return hardware_drift_warnings(
        plan.saved_hardware_profile,
        plan.hardware_observation,
    )


def _hardware_prerequisites(
    plan: ResourcePlan, current: HardwareObservation
) -> tuple[str, ...]:
    observation = current
    budget = plan.budget
    prerequisites: list[str] = []
    if observation.logical_cpu_count < budget.peak_cpu_count:
        prerequisites.append(
            f"Provide at least {budget.peak_cpu_count} logical CPU cores."
        )
    if observation.total_memory_bytes < budget.peak_memory_bytes:
        prerequisites.append(
            f"Provide at least {budget.peak_memory_bytes} bytes of memory."
        )
    if observation.free_disk_bytes < budget.peak_temporary_disk_bytes:
        prerequisites.append(
            f"Free at least {budget.peak_temporary_disk_bytes} bytes of project disk space."
        )
    if budget.peak_gpu_count and observation.gpu_available is not True:
        prerequisites.append(
            f"Provide at least {budget.peak_gpu_count} available GPU."
        )
    return tuple(prerequisites)


def _validated_config_required_paths(
    project: "ResearchProject",
    bindings: Mapping[str, ResourceBinding],
    issues: list["ValidationIssue"],
) -> tuple[str, ...] | None:
    """Read required paths only from the current validated, hash-bound config."""
    expected_path = _REQUIRED_BINDINGS["config"]
    binding = bindings.get("config")
    artifact = project.state.artifacts.get(expected_path)
    if binding is None or artifact is None:
        return None
    try:
        config_path = resolve_project_artifact(project.root, expected_path)
        payload = config_path.read_bytes()
    except (OSError, ValueError) as error:
        issues.append(
            _validation_issue(
                "config_input_contract_unreadable",
                "bindings.config.path",
                str(error),
            )
        )
        return None
    digest = hashlib.sha256(payload).hexdigest()
    if (
        binding.path != expected_path
        or binding.sha256 != digest
        or artifact.path != expected_path
        or artifact.sha256 != digest
        or artifact.size != len(payload)
    ):
        return None
    try:
        config = json.loads(payload)
        input_contract = config["input_contract"]
        required_paths = input_contract["required_paths"]
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(
            _validation_issue(
                "config_input_contract_unreadable",
                "bindings.config.path",
                f"validated config input contract cannot be read: {error}",
            )
        )
        return None
    if (
        not isinstance(required_paths, list)
        or not all(isinstance(path, str) and path for path in required_paths)
    ):
        issues.append(
            _validation_issue(
                "config_input_contract_unreadable",
                "bindings.config.path",
                "validated config input_contract.required_paths must be a string array",
            )
        )
        return None
    return tuple(required_paths)


def validate_stage_eleven(
    project: "ResearchProject", raw: object
) -> tuple[ResourcePlan | None, tuple["ValidationIssue", ...]]:
    """Validate a closed resource plan against current project and filesystem truth."""
    outcome = validate_resource_plan_structure(raw)
    if not outcome.valid:
        return None, tuple(_as_validation_issue(issue) for issue in outcome.issues)
    plan = outcome.plan
    assert plan is not None
    issues: list[ValidationIssue] = []

    if plan.project_id != project.state.project_id:
        issues.append(
            _validation_issue(
                "project_id_mismatch",
                "project_id",
                "project_id must match the current project",
            )
        )

    bindings = {binding.name: binding for binding in plan.bindings}
    if set(bindings) != set(_REQUIRED_BINDINGS):
        issues.append(
            _validation_issue(
                "binding_set_mismatch",
                "bindings",
                "bindings must contain exactly design, package_manifest, config, and hardware_profile",
            )
        )
    for name, expected_path in _REQUIRED_BINDINGS.items():
        binding = bindings.get(name)
        if binding is None:
            continue
        binding_path = f"bindings.{name}"
        if binding.path != expected_path:
            issues.append(
                _validation_issue(
                    "binding_path_mismatch",
                    f"{binding_path}.path",
                    f"binding path must be {expected_path}",
                )
            )
            continue
        try:
            artifact_path = resolve_project_artifact(project.root, expected_path)
            actual_hash = _sha256(artifact_path) if artifact_path.is_file() else None
        except (OSError, ValueError) as error:
            issues.append(
                _validation_issue(
                    "unsafe_binding_path", f"{binding_path}.path", str(error)
                )
            )
            continue
        if actual_hash != binding.sha256:
            issues.append(
                _validation_issue(
                    "binding_hash_mismatch",
                    f"{binding_path}.sha256",
                    "binding hash does not match the current regular file",
                )
            )
        persisted = project.state.artifacts.get(expected_path)
        if (
            persisted is None
            or persisted.path != expected_path
            or persisted.sha256 != binding.sha256
        ):
            issues.append(
                _validation_issue(
                    "binding_state_mismatch",
                    f"{binding_path}.sha256",
                    "binding hash does not match the validated durable artifact",
                )
            )

    config_required_paths = _validated_config_required_paths(
        project,
        bindings,
        issues,
    )
    if config_required_paths is not None:
        config_required_set = set(config_required_paths)
        plan_required_set = {
            input_fact.path for input_fact in plan.inputs if input_fact.required
        }
        for index, input_fact in enumerate(plan.inputs):
            if input_fact.path in config_required_set and not input_fact.required:
                issues.append(
                    _validation_issue(
                        "required_input_flag_mismatch",
                        f"inputs[{index}].required",
                        "config-required input paths must be marked required",
                    )
                )
        if plan_required_set != config_required_set:
            issues.append(
                _validation_issue(
                    "required_input_set_mismatch",
                    "inputs",
                    "required input paths must exactly equal config input_contract.required_paths",
                )
            )

    try:
        hardware_profile_path = resolve_project_artifact(
            project.root, _REQUIRED_BINDINGS["hardware_profile"]
        )
        saved_profile = json.loads(hardware_profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        issues.append(
            _validation_issue(
                "saved_profile_unreadable", "saved_hardware_profile", str(error)
            )
        )
    else:
        if _freeze_json(saved_profile) != plan.saved_hardware_profile:
            issues.append(
                _validation_issue(
                    "saved_profile_mismatch",
                    "saved_hardware_profile",
                    "saved_hardware_profile must equal scope/hardware_profile.json",
                )
            )

    observation = plan.hardware_observation
    current = observe_local_hardware(project.root)
    observation_facts = (
        "logical_cpu_count",
        "total_memory_bytes",
        "platform",
        "architecture",
    )
    for field in observation_facts:
        if getattr(observation, field) != getattr(current, field):
            issues.append(
                _validation_issue(
                    "hardware_observation_mismatch",
                    f"hardware_observation.{field}",
                    "passive hardware fact does not match the current host",
                )
            )
    if (
        observation.free_disk_bytes
        > current.free_disk_bytes + _FREE_DISK_SNAPSHOT_TOLERANCE
    ):
        issues.append(
            _validation_issue(
                "hardware_observation_mismatch",
                "hardware_observation.free_disk_bytes",
                "declared free disk exceeds the current passive observation",
            )
        )
    if observation.gpu_available != current.gpu_available:
        issues.append(
            _validation_issue(
                "hardware_observation_mismatch",
                "hardware_observation.gpu_available",
                "GPU availability does not match the current passive observation",
            )
        )
    if observation.method != "python_stdlib_passive":
        issues.append(
            _validation_issue(
                "invalid_observation_method",
                "hardware_observation.method",
                "hardware observation must use python_stdlib_passive",
            )
        )
    try:
        observed_at = datetime.fromisoformat(observation.observed_at)
    except ValueError:
        observed_at = None
    if observed_at is None or observed_at.tzinfo is None:
        issues.append(
            _validation_issue(
                "invalid_observation_time",
                "hardware_observation.observed_at",
                "observed_at must be an ISO-8601 timestamp with a timezone",
            )
        )

    prerequisites = list(_hardware_prerequisites(plan, current))
    for index, input_fact in enumerate(plan.inputs):
        base_path = f"inputs[{index}]"
        if input_fact.license_status not in _LICENSE_VALUES:
            issues.append(
                _validation_issue(
                    "invalid_license_status",
                    f"{base_path}.license_status",
                    "license_status must be confirmed, not_required, or unconfirmed",
                )
            )
        try:
            input_path = resolve_project_artifact(project.root, input_fact.path)
        except (OSError, ValueError) as error:
            issues.append(
                _validation_issue("unsafe_input_path", f"{base_path}.path", str(error))
            )
            continue
        try:
            exists = input_path.exists()
            is_regular = exists and stat.S_ISREG(input_path.stat().st_mode)
            size_bytes = input_path.stat().st_size if is_regular else 0
            digest = _sha256(input_path) if is_regular else None
        except OSError as error:
            issues.append(
                _validation_issue(
                    "input_fact_unreadable", f"{base_path}.path", str(error)
                )
            )
            continue
        actual_facts = {
            "exists": exists,
            "is_regular_file": is_regular,
            "size_bytes": size_bytes,
            "sha256": digest,
        }
        for field, actual in actual_facts.items():
            if getattr(input_fact, field) != actual:
                issues.append(
                    _validation_issue(
                        "input_fact_mismatch",
                        f"{base_path}.{field}",
                        "declared input fact does not match the current filesystem",
                    )
                )
        if input_fact.required:
            if not exists:
                prerequisites.append(
                    f"Provide required input file at {input_fact.path}."
                )
            elif not is_regular:
                prerequisites.append(
                    f"Replace {input_fact.path} with a regular input file."
                )
            if input_fact.license_status == "unconfirmed":
                prerequisites.append(
                    "Confirm license authorization for required input "
                    f"{input_fact.path}."
                )

    expected_prerequisites = tuple(sorted(set(prerequisites)))
    if plan.unmet_prerequisites != expected_prerequisites:
        issues.append(
            _validation_issue(
                "unmet_prerequisites_mismatch",
                "unmet_prerequisites",
                "unmet_prerequisites must exactly equal the sorted actionable requirements",
            )
        )
    expected_readiness = (
        "needs_input" if expected_prerequisites else "ready_for_execution"
    )
    if plan.readiness != expected_readiness:
        issues.append(
            _validation_issue(
                "readiness_mismatch",
                "readiness",
                f"readiness must be {expected_readiness}",
            )
        )

    expected_warnings = _hardware_drift_warnings(plan)
    if plan.warnings != expected_warnings:
        issues.append(
            _validation_issue(
                "warnings_mismatch",
                "warnings",
                "warnings must exactly equal the sorted saved-profile drift warnings",
            )
        )

    try:
        result_path = resolve_project_artifact(project.root, EXPERIMENT_RESULT_PATH)
        result_exists = result_path.exists()
    except (OSError, ValueError):
        result_exists = True
    if result_exists:
        issues.append(
            _validation_issue(
                "preexisting_result",
                EXPERIMENT_RESULT_PATH,
                "experiment results must not exist before execution approval",
            )
        )

    return plan, tuple(issues)


def validated_execution_readiness(
    project: "ResearchProject",
) -> tuple[str | None, tuple[str, ...], bool]:
    """Read readiness only from the intact resource plan persisted by validation."""
    artifact = project.state.artifacts.get(RESOURCE_PLAN_PATH)
    if artifact is None:
        return None, (), False
    try:
        path = resolve_project_artifact(project.root, artifact.path)
        stat_result = path.stat()
        if (
            artifact.path != RESOURCE_PLAN_PATH
            or not path.is_file()
            or stat_result.st_size != artifact.size
            or _sha256(path) != artifact.sha256
        ):
            return None, (), False
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None, (), False
    outcome = validate_resource_plan_structure(raw)
    if not outcome.valid or outcome.plan is None:
        return None, (), False
    plan = outcome.plan
    return (
        plan.readiness,
        plan.unmet_prerequisites,
        plan.readiness == "ready_for_execution" and not plan.unmet_prerequisites,
    )
