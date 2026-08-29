"""Fixed local NumPy Ridge execution for synthetic development fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from .events import EvaluationEvent, event_log_for
from .execution_gate import (
    DevelopmentInputValidationError,
    ValidatedDevelopmentInput,
    _read_project_file_snapshot,
    validate_development_input,
)
from .paths import validate_relative_path
from .persistence import _fsync_directory
from .project import ResearchProject


_ALLOWED_SPLIT_ROLES = ("train", "validation", "calibration", "test")
_FEATURE_IDENTIFIER_FIELDS = frozenset({"dataset_id", "condition_id", "cell_id"})
_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "development_only",
        "evidence_eligible",
        "input_manifest",
        "model",
        "predictor_names",
        "numpy_version",
        "dataset_results",
        "aggregate_metrics",
        "leakage_audit",
        "runtime",
    }
)


class _DevelopmentExecutionError(ValueError):
    """A bounded development-input failure with a machine-readable category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class DevelopmentRunStatus:
    """Outcome metadata for one development-only local execution."""

    readiness: str
    approval_eligible: bool
    input_manifest_path: str
    input_manifest_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "input_manifest_path": self.input_manifest_path,
            "input_manifest_sha256": self.input_manifest_sha256,
        }


@dataclass(frozen=True)
class DevelopmentResultValidationStatus:
    """Identity and readiness of one independently validated development result."""

    readiness: str
    approval_eligible: bool
    result_path: str
    result_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
        }


def _finite_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise _DevelopmentExecutionError("invalid_numeric_value") from error
    if not math.isfinite(parsed):
        raise _DevelopmentExecutionError("invalid_numeric_value")
    return parsed


def _manifest_field(manifest: Mapping[str, object], section: str, field: str) -> str:
    raw_section = manifest.get(section)
    if not isinstance(raw_section, Mapping) or not isinstance(raw_section.get(field), str):
        raise _DevelopmentExecutionError("invalid_development_manifest")
    return raw_section[field]


def _predictor_names(validated: ValidatedDevelopmentInput) -> tuple[str, ...]:
    cycle_field = _manifest_field(
        validated.manifest, "feature_cutoff", "measurement_cycle_field"
    )
    if not validated.feature_rows:
        raise _DevelopmentExecutionError("missing_predictors")
    label_field = _manifest_field(validated.manifest, "labels", "field")
    cutoff_field = _manifest_field(
        validated.manifest, "feature_cutoff", "cutoff_field"
    )
    forbidden = {label_field, "cycle_life_cycles", "split_role", cutoff_field}
    if forbidden.intersection(validated.feature_rows[0]):
        raise _DevelopmentExecutionError("feature_metadata_leakage")
    names = tuple(
        field
        for field in validated.feature_rows[0]
        if field not in _FEATURE_IDENTIFIER_FIELDS and field != cycle_field
    )
    if not names:
        raise _DevelopmentExecutionError("missing_predictors")
    return names


def _dataset_rows(
    np: Any,
    validated: ValidatedDevelopmentInput,
    predictor_names: tuple[str, ...],
) -> dict[str, list[tuple[Mapping[str, str], object, float]]]:
    manifest = validated.manifest
    label_field = _manifest_field(manifest, "labels", "field")
    cutoff_field = _manifest_field(manifest, "feature_cutoff", "cutoff_field")
    cycle_field = _manifest_field(manifest, "feature_cutoff", "measurement_cycle_field")
    features_by_cell: dict[str, list[Mapping[str, str]]] = {}
    for feature in validated.feature_rows:
        features_by_cell.setdefault(feature["cell_id"], []).append(feature)

    datasets: dict[str, list[tuple[Mapping[str, str], object, float]]] = {}
    for cell in validated.cell_rows:
        role = cell.get("split_role")
        if role not in _ALLOWED_SPLIT_ROLES:
            raise _DevelopmentExecutionError("invalid_split_role")
        label = _finite_float(cell.get(label_field))
        try:
            cutoff = int(cell[cutoff_field])
        except (KeyError, TypeError, ValueError) as error:
            raise _DevelopmentExecutionError("invalid_development_manifest") from error
        rows = features_by_cell.get(cell["cell_id"], [])
        if not rows:
            raise _DevelopmentExecutionError("missing_feature_rows")
        feature_values: list[list[float]] = []
        for feature in rows:
            try:
                cycle_index = int(feature[cycle_field])
            except (KeyError, TypeError, ValueError) as error:
                raise _DevelopmentExecutionError("invalid_development_manifest") from error
            if cycle_index > cutoff:
                raise _DevelopmentExecutionError("feature_cutoff_violation")
            feature_values.append([_finite_float(feature.get(name)) for name in predictor_names])
        try:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                feature_array = np.asarray(feature_values, dtype=float)
                _require_finite_array(np, feature_array)
                predictors = feature_array.mean(axis=0)
                _require_finite_array(np, predictors)
        except (FloatingPointError, OverflowError) as error:
            raise _DevelopmentExecutionError("numerical_error") from error
        datasets.setdefault(cell["dataset_id"], []).append((cell, predictors, label))
    return datasets


def _require_finite_array(np: Any, value: object) -> None:
    try:
        finite = bool(np.isfinite(value).all())
    except (TypeError, ValueError, FloatingPointError, OverflowError) as error:
        raise _DevelopmentExecutionError("numerical_error") from error
    if not finite:
        raise _DevelopmentExecutionError("numerical_error")


def _metric_values(np: Any, predictions: object, labels: object) -> tuple[float, float]:
    try:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            _require_finite_array(np, predictions)
            _require_finite_array(np, labels)
            residuals = predictions - labels
            _require_finite_array(np, residuals)
            squared = np.square(residuals)
            _require_finite_array(np, squared)
            mae = float(np.abs(residuals).mean())
            rmse = float(np.sqrt(squared.mean()))
    except (FloatingPointError, OverflowError) as error:
        raise _DevelopmentExecutionError("numerical_error") from error
    if not math.isfinite(mae) or not math.isfinite(rmse):
        raise _DevelopmentExecutionError("numerical_error")
    return mae, rmse


def _fit_dataset(
    np: Any,
    dataset_id: str,
    rows: list[tuple[Mapping[str, str], object, float]],
) -> tuple[dict[str, object], object, object]:
    by_role = {role: [row for row in rows if row[0]["split_role"] == role] for role in _ALLOWED_SPLIT_ROLES}
    if not by_role["train"]:
        raise _DevelopmentExecutionError("missing_train_cells")
    if not by_role["test"]:
        raise _DevelopmentExecutionError("missing_test_cells")

    train_x = np.asarray([row[1] for row in by_role["train"]], dtype=float)
    train_y = np.asarray([row[2] for row in by_role["train"]], dtype=float)
    test_x = np.asarray([row[1] for row in by_role["test"]], dtype=float)
    test_y = np.asarray([row[2] for row in by_role["test"]], dtype=float)
    try:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            for array in (train_x, train_y, test_x, test_y):
                _require_finite_array(np, array)
            mean = train_x.mean(axis=0)
            raw_std = train_x.std(axis=0)
            _require_finite_array(np, mean)
            _require_finite_array(np, raw_std)
            std = np.where(raw_std == 0.0, 1.0, raw_std)
            standardized_train = (train_x - mean) / std
            standardized_test = (test_x - mean) / std
            _require_finite_array(np, standardized_train)
            _require_finite_array(np, standardized_test)
            design = np.column_stack([np.ones(len(train_x)), standardized_train])
            penalty = np.eye(design.shape[1])
            penalty[0, 0] = 0.0
            gram = design.T @ design + 1.0 * penalty
            target = design.T @ train_y
            _require_finite_array(np, design)
            _require_finite_array(np, gram)
            _require_finite_array(np, target)
            beta = np.linalg.solve(gram, target)
            _require_finite_array(np, beta)
            test_design = np.column_stack([np.ones(len(test_x)), standardized_test])
            _require_finite_array(np, test_design)
            predictions = test_design @ beta
            _require_finite_array(np, predictions)
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError) as error:
        raise _DevelopmentExecutionError("numerical_error") from error
    mae, rmse = _metric_values(np, predictions, test_y)
    result = {
        "dataset_id": dataset_id,
        "role_counts": {role: len(by_role[role]) for role in _ALLOWED_SPLIT_ROLES},
        "group_counts": {
            role: len({row[0]["condition_id"] for row in by_role[role]})
            for role in _ALLOWED_SPLIT_ROLES
        },
        "mae_cycles": mae,
        "rmse_cycles": rmse,
    }
    return result, predictions, test_y


def _result_path(project: ResearchProject) -> Path:
    return project.root / "experiment" / "dev_results.json"


def _load_numpy(project_root: Path) -> Any:
    project_root = project_root.resolve()
    original_path = list(sys.path)
    safe_path: list[str] = []
    for entry in original_path:
        try:
            resolved = Path(entry or os.getcwd()).resolve()
            resolved.relative_to(project_root)
        except ValueError:
            safe_path.append(entry)
    sys.path[:] = safe_path
    try:
        module = importlib.import_module("numpy")
    except ImportError as error:
        raise _DevelopmentExecutionError("numpy_unavailable") from error
    finally:
        sys.path[:] = original_path
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise _DevelopmentExecutionError("numpy_unavailable")
    try:
        Path(module_file).resolve().relative_to(project_root)
    except ValueError:
        return module
    raise _DevelopmentExecutionError("numpy_unavailable")


def _validate_finite_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _DevelopmentExecutionError("numerical_error")
        return
    if isinstance(value, list):
        for item in value:
            _validate_finite_json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_finite_json(item)
        return
    raise _DevelopmentExecutionError("invalid_result_payload")


def _closed_mapping(value: object, keys: set[str] | frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise _DevelopmentExecutionError("invalid_result_payload")
    return value


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_result_payload(payload: dict[str, object]) -> None:
    _closed_mapping(payload, _RESULT_KEYS)
    if (
        payload["schema_version"] != 1
        or not isinstance(payload["project_id"], str)
        or payload["development_only"] is not True
        or payload["evidence_eligible"] is not False
        or not isinstance(payload["numpy_version"], str)
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    manifest = _closed_mapping(payload["input_manifest"], {"path", "sha256"})
    manifest_digest = manifest["sha256"]
    if (
        not isinstance(manifest["path"], str)
        or not isinstance(manifest_digest, str)
        or len(manifest_digest) != 64
        or any(character not in "0123456789abcdef" for character in manifest_digest)
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    if _closed_mapping(payload["model"], {"name", "alpha", "implementation"}) != {
        "name": "ridge",
        "alpha": 1.0,
        "implementation": "numpy_closed_form",
    }:
        raise _DevelopmentExecutionError("invalid_result_payload")
    predictor_names = payload["predictor_names"]
    if (
        not isinstance(predictor_names, list)
        or not predictor_names
        or not all(isinstance(name, str) and name for name in predictor_names)
        or len(set(predictor_names)) != len(predictor_names)
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    dataset_results = payload["dataset_results"]
    if not isinstance(dataset_results, list) or not dataset_results:
        raise _DevelopmentExecutionError("invalid_result_payload")
    seen_dataset_ids: set[str] = set()
    for raw_result in dataset_results:
        result = _closed_mapping(
            raw_result,
            {"dataset_id", "role_counts", "group_counts", "mae_cycles", "rmse_cycles"},
        )
        dataset_id = result["dataset_id"]
        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in seen_dataset_ids:
            raise _DevelopmentExecutionError("invalid_result_payload")
        seen_dataset_ids.add(dataset_id)
        for count_key in ("role_counts", "group_counts"):
            counts = _closed_mapping(result[count_key], set(_ALLOWED_SPLIT_ROLES))
            if not all(
                isinstance(count, int) and not isinstance(count, bool) and count >= 0
                for count in counts.values()
            ):
                raise _DevelopmentExecutionError("invalid_result_payload")
        if (
            not _is_finite_number(result["mae_cycles"])
            or not _is_finite_number(result["rmse_cycles"])
            or result["mae_cycles"] < 0
            or result["rmse_cycles"] < result["mae_cycles"]
        ):
            raise _DevelopmentExecutionError("invalid_result_payload")
    aggregate = _closed_mapping(
        payload["aggregate_metrics"], {"mae_cycles", "rmse_cycles"}
    )
    if (
        not all(_is_finite_number(metric) for metric in aggregate.values())
        or aggregate["mae_cycles"] < 0
        or aggregate["rmse_cycles"] < aggregate["mae_cycles"]
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    leakage = _closed_mapping(
        payload["leakage_audit"],
        {
            "cell_overlap_count",
            "group_overlap_count",
            "feature_cutoff_violation_count",
        },
    )
    if not all(
        isinstance(count, int) and not isinstance(count, bool) and count >= 0
        for count in leakage.values()
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    runtime = _closed_mapping(payload["runtime"], {"elapsed_seconds", "max_seconds"})
    if (
        not _is_finite_number(runtime["elapsed_seconds"])
        or runtime["elapsed_seconds"] < 0
        or not isinstance(runtime["max_seconds"], int)
        or isinstance(runtime["max_seconds"], bool)
        or runtime["max_seconds"] <= 0
        or runtime["elapsed_seconds"] > runtime["max_seconds"]
    ):
        raise _DevelopmentExecutionError("invalid_result_payload")
    _validate_finite_json(payload)


def _strict_result_json(snapshot: bytes) -> dict[str, object]:
    def reject_constant(_value: str) -> object:
        raise _DevelopmentExecutionError("invalid_result_payload")

    try:
        payload = json.loads(snapshot.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise _DevelopmentExecutionError("invalid_result_payload") from error
    if not isinstance(payload, dict):
        raise _DevelopmentExecutionError("invalid_result_payload")
    _validate_result_payload(payload)
    return payload


def _declared_dataset_ids(manifest: Mapping[str, object]) -> set[str]:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, tuple):
        raise _DevelopmentExecutionError("invalid_development_manifest")
    identifiers: set[str] = set()
    for dataset in datasets:
        if not isinstance(dataset, Mapping):
            raise _DevelopmentExecutionError("invalid_development_manifest")
        dataset_id = dataset.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in identifiers:
            raise _DevelopmentExecutionError("invalid_development_manifest")
        identifiers.add(dataset_id)
    return identifiers


def _expected_dataset_counts(
    validated: ValidatedDevelopmentInput,
) -> dict[str, dict[str, dict[str, int]]]:
    expected: dict[str, dict[str, dict[str, int]]] = {}
    groups: dict[str, dict[str, set[str]]] = {}
    for row in validated.cell_rows:
        dataset_id = row.get("dataset_id")
        role = row.get("split_role")
        group_id = row.get("condition_id")
        if (
            not isinstance(dataset_id, str)
            or role not in _ALLOWED_SPLIT_ROLES
            or not isinstance(group_id, str)
        ):
            raise _DevelopmentExecutionError("invalid_development_manifest")
        counts = expected.setdefault(
            dataset_id,
            {
                "role_counts": {name: 0 for name in _ALLOWED_SPLIT_ROLES},
                "group_counts": {name: 0 for name in _ALLOWED_SPLIT_ROLES},
            },
        )
        counts["role_counts"][role] += 1
        groups.setdefault(dataset_id, {}).setdefault(role, set()).add(group_id)
    for dataset_id, by_role in groups.items():
        for role in _ALLOWED_SPLIT_ROLES:
            expected[dataset_id]["group_counts"][role] = len(by_role.get(role, set()))
    return expected


def validate_development_result(
    project: ResearchProject,
    result_path: str,
) -> DevelopmentResultValidationStatus:
    """Validate a saved development result without rerunning or promoting it."""
    normalized_result_path = validate_relative_path(result_path, kind="artifact")
    try:
        snapshot = _read_project_file_snapshot(project.root, normalized_result_path)
    except (OSError, ValueError) as error:
        raise _DevelopmentExecutionError("invalid_development_result_file") from error
    result_sha256 = hashlib.sha256(snapshot).hexdigest()
    payload = _strict_result_json(snapshot)
    if payload["project_id"] != project.state.project_id:
        raise _DevelopmentExecutionError("development_result_project_mismatch")

    result_manifest = payload["input_manifest"]
    assert isinstance(result_manifest, dict)
    manifest_path = result_manifest["path"]
    assert isinstance(manifest_path, str)
    _status, validated = validate_development_input(
        project, manifest_path, record_event=False
    )
    if result_manifest["sha256"] != validated.manifest_sha256:
        raise _DevelopmentExecutionError("development_result_manifest_mismatch")

    expected = _expected_dataset_counts(validated)
    if set(expected) != _declared_dataset_ids(validated.manifest):
        raise _DevelopmentExecutionError("development_result_dataset_mismatch")
    dataset_results = payload["dataset_results"]
    assert isinstance(dataset_results, list)
    actual = {result["dataset_id"]: result for result in dataset_results}
    if set(actual) != set(expected):
        raise _DevelopmentExecutionError("development_result_dataset_mismatch")
    for dataset_id, counts in expected.items():
        result = actual[dataset_id]
        if (
            result["role_counts"] != counts["role_counts"]
            or result["group_counts"] != counts["group_counts"]
        ):
            raise _DevelopmentExecutionError("development_result_count_mismatch")
    if any(payload["leakage_audit"].values()):
        raise _DevelopmentExecutionError("development_result_leakage_detected")

    event_log_for(project.root).append(
        EvaluationEvent.create(
            "development_result_validated",
            project.state.project_id,
            {
                "input_manifest_path": validated.manifest_path,
                "input_manifest_sha256": validated.manifest_sha256,
                "result_path": normalized_result_path,
                "result_sha256": result_sha256,
            },
        )
    )
    return DevelopmentResultValidationStatus(
        readiness="development_result_valid",
        approval_eligible=False,
        result_path=normalized_result_path,
        result_sha256=result_sha256,
    )


def _stage_result_json(
    destination: Path, payload: dict[str, object]
) -> tuple[Path, str]:
    _validate_result_payload(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="dev-results-",
            suffix=".tmp",
            delete=False,
            dir=destination.parent,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        return temporary_path, digest
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _commit_staged_result(temporary_path: Path, destination: Path) -> None:
    temporary_path.replace(destination)
    _fsync_directory(destination.parent)


def _append_execution_failure(
    project: ResearchProject,
    input_manifest_path: str,
    validated: ValidatedDevelopmentInput | None,
    error: ValueError,
) -> None:
    payload: dict[str, object] = {
        "error_category": "development_input_validation_failed"
    }
    if isinstance(error, _DevelopmentExecutionError):
        payload["error_category"] = error.category
    if validated is not None:
        payload["input_manifest_path"] = validated.manifest_path
        payload["input_manifest_sha256"] = validated.manifest_sha256
    elif isinstance(error, DevelopmentInputValidationError):
        if error.manifest_path:
            payload["input_manifest_path"] = error.manifest_path
        if error.manifest_sha256:
            payload["input_manifest_sha256"] = error.manifest_sha256
    elif isinstance(input_manifest_path, str) and input_manifest_path:
        payload["input_manifest_path"] = input_manifest_path
    event_log_for(project.root).append(
        EvaluationEvent.create(
            "development_execution_failed",
            project.state.project_id,
            payload,
        )
    )


def run_development_experiment(
    project: ResearchProject,
    input_manifest_path: str,
    max_seconds: int = 120,
    *,
    clock: object = time.monotonic,
) -> DevelopmentRunStatus:
    """Run deterministic Ridge evaluation on validated synthetic development data."""
    validated: ValidatedDevelopmentInput | None = None
    staged_result: Path | None = None
    try:
        if (
            not isinstance(max_seconds, int)
            or isinstance(max_seconds, bool)
            or max_seconds <= 0
        ):
            raise _DevelopmentExecutionError("invalid_max_seconds")
        started = clock()

        def check_deadline() -> float:
            observed = clock() - started
            if observed > max_seconds:
                raise _DevelopmentExecutionError("development_timeout")
            return observed

        _status, validated = validate_development_input(
            project,
            input_manifest_path,
            record_event=False,
        )
        check_deadline()
        np = _load_numpy(project.root)
        predictor_names = _predictor_names(validated)
        datasets = _dataset_rows(np, validated, predictor_names)
        check_deadline()
        dataset_results: list[dict[str, object]] = []
        predictions: list[object] = []
        labels: list[object] = []
        for dataset_id in sorted(datasets):
            result, dataset_predictions, dataset_labels = _fit_dataset(
                np,
                dataset_id,
                datasets[dataset_id],
            )
            dataset_results.append(result)
            predictions.append(dataset_predictions)
            labels.append(dataset_labels)
            check_deadline()
        aggregate_predictions = np.concatenate(predictions)
        aggregate_labels = np.concatenate(labels)
        _require_finite_array(np, aggregate_predictions)
        _require_finite_array(np, aggregate_labels)
        aggregate_mae, aggregate_rmse = _metric_values(
            np,
            aggregate_predictions,
            aggregate_labels,
        )
        check_deadline()
        elapsed_seconds = clock() - started
        if elapsed_seconds > max_seconds:
            raise _DevelopmentExecutionError("development_timeout")
        result_payload: dict[str, object] = {
            "schema_version": 1,
            "project_id": project.state.project_id,
            "development_only": True,
            "evidence_eligible": False,
            "input_manifest": {
                "path": validated.manifest_path,
                "sha256": validated.manifest_sha256,
            },
            "model": {
                "name": "ridge",
                "alpha": 1.0,
                "implementation": "numpy_closed_form",
            },
            "predictor_names": list(predictor_names),
            "numpy_version": np.__version__,
            "dataset_results": dataset_results,
            "aggregate_metrics": {
                "mae_cycles": aggregate_mae,
                "rmse_cycles": aggregate_rmse,
            },
            "leakage_audit": {
                "cell_overlap_count": 0,
                "group_overlap_count": 0,
                "feature_cutoff_violation_count": 0,
            },
            "runtime": {
                "elapsed_seconds": elapsed_seconds,
                "max_seconds": max_seconds,
            },
        }
        destination = _result_path(project)
        staged_result, result_sha256 = _stage_result_json(destination, result_payload)
        final_elapsed_seconds = check_deadline()
        if final_elapsed_seconds != elapsed_seconds:
            staged_result.unlink(missing_ok=True)
            staged_result = None
            result_payload["runtime"] = {
                "elapsed_seconds": final_elapsed_seconds,
                "max_seconds": max_seconds,
            }
            staged_result, result_sha256 = _stage_result_json(
                destination, result_payload
            )
        _commit_staged_result(staged_result, destination)
        staged_result = None
        event_log_for(project.root).append(
            EvaluationEvent.create(
                "development_execution_completed",
                project.state.project_id,
                {
                    "input_manifest_path": validated.manifest_path,
                    "input_manifest_sha256": validated.manifest_sha256,
                    "result_path": "experiment/dev_results.json",
                    "result_sha256": result_sha256,
                    "elapsed_seconds": final_elapsed_seconds,
                    "dataset_count": len(dataset_results),
                    "cell_count": len(validated.cell_rows),
                },
            )
        )
        return DevelopmentRunStatus(
            readiness="development_run_complete",
            approval_eligible=False,
            input_manifest_path=validated.manifest_path,
            input_manifest_sha256=validated.manifest_sha256,
        )
    except ValueError as error:
        _append_execution_failure(project, input_manifest_path, validated, error)
        raise
    finally:
        if staged_result is not None:
            staged_result.unlink(missing_ok=True)
