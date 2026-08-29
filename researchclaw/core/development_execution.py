"""Fixed local NumPy Ridge execution for synthetic development fixtures."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time

import numpy as np

from .execution_gate import ValidatedDevelopmentInput, validate_development_input
from .project import ResearchProject


_ALLOWED_SPLIT_ROLES = ("train", "validation", "calibration", "test")
_FEATURE_IDENTIFIER_FIELDS = frozenset({"dataset_id", "condition_id", "cell_id"})


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


def _finite_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise _DevelopmentExecutionError("invalid_numeric_value") from error
    if not math.isfinite(parsed):
        raise _DevelopmentExecutionError("invalid_numeric_value")
    return parsed


def _manifest_field(manifest: dict[str, object], section: str, field: str) -> str:
    raw_section = manifest.get(section)
    if not isinstance(raw_section, dict) or not isinstance(raw_section.get(field), str):
        raise _DevelopmentExecutionError("invalid_development_manifest")
    return raw_section[field]


def _predictor_names(validated: ValidatedDevelopmentInput) -> tuple[str, ...]:
    cycle_field = _manifest_field(
        validated.manifest, "feature_cutoff", "measurement_cycle_field"
    )
    if not validated.feature_rows:
        raise _DevelopmentExecutionError("missing_predictors")
    names = tuple(
        field
        for field in validated.feature_rows[0]
        if field not in _FEATURE_IDENTIFIER_FIELDS and field != cycle_field
    )
    if not names:
        raise _DevelopmentExecutionError("missing_predictors")
    return names


def _dataset_rows(
    validated: ValidatedDevelopmentInput,
    predictor_names: tuple[str, ...],
) -> dict[str, list[tuple[dict[str, str], np.ndarray, float]]]:
    manifest = validated.manifest
    label_field = _manifest_field(manifest, "labels", "field")
    cutoff_field = _manifest_field(manifest, "feature_cutoff", "cutoff_field")
    cycle_field = _manifest_field(manifest, "feature_cutoff", "measurement_cycle_field")
    features_by_cell: dict[str, list[dict[str, str]]] = {}
    for feature in validated.feature_rows:
        features_by_cell.setdefault(feature["cell_id"], []).append(feature)

    datasets: dict[str, list[tuple[dict[str, str], np.ndarray, float]]] = {}
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
        predictors = np.asarray(feature_values, dtype=float).mean(axis=0)
        datasets.setdefault(cell["dataset_id"], []).append((cell, predictors, label))
    return datasets


def _metric_values(predictions: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    residuals = predictions - labels
    return float(np.abs(residuals).mean()), float(np.sqrt(np.square(residuals).mean()))


def _fit_dataset(
    dataset_id: str,
    rows: list[tuple[dict[str, str], np.ndarray, float]],
) -> tuple[dict[str, object], np.ndarray, np.ndarray]:
    by_role = {role: [row for row in rows if row[0]["split_role"] == role] for role in _ALLOWED_SPLIT_ROLES}
    if not by_role["train"]:
        raise _DevelopmentExecutionError("missing_train_cells")
    if not by_role["test"]:
        raise _DevelopmentExecutionError("missing_test_cells")

    train_x = np.asarray([row[1] for row in by_role["train"]], dtype=float)
    train_y = np.asarray([row[2] for row in by_role["train"]], dtype=float)
    test_x = np.asarray([row[1] for row in by_role["test"]], dtype=float)
    test_y = np.asarray([row[2] for row in by_role["test"]], dtype=float)
    mean = train_x.mean(axis=0)
    std = np.where(train_x.std(axis=0) == 0.0, 1.0, train_x.std(axis=0))
    design = np.column_stack([np.ones(len(train_x)), (train_x - mean) / std])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    try:
        beta = np.linalg.solve(
            design.T @ design + 1.0 * penalty,
            design.T @ train_y,
        )
    except np.linalg.LinAlgError as error:
        raise _DevelopmentExecutionError("numerical_error") from error
    test_design = np.column_stack([np.ones(len(test_x)), (test_x - mean) / std])
    predictions = test_design @ beta
    mae, rmse = _metric_values(predictions, test_y)
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


def run_development_experiment(
    project: ResearchProject,
    input_manifest_path: str,
    max_seconds: int = 120,
    *,
    clock: object = time.monotonic,
) -> DevelopmentRunStatus:
    """Run deterministic Ridge evaluation on validated synthetic development data."""
    del max_seconds, clock
    _status, validated = validate_development_input(
        project,
        input_manifest_path,
        record_event=False,
    )
    predictor_names = _predictor_names(validated)
    datasets = _dataset_rows(validated, predictor_names)
    dataset_results: list[dict[str, object]] = []
    predictions: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for dataset_id in sorted(datasets):
        result, dataset_predictions, dataset_labels = _fit_dataset(
            dataset_id,
            datasets[dataset_id],
        )
        dataset_results.append(result)
        predictions.append(dataset_predictions)
        labels.append(dataset_labels)
    aggregate_mae, aggregate_rmse = _metric_values(
        np.concatenate(predictions), np.concatenate(labels)
    )
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
    }
    destination = _result_path(project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result_payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return DevelopmentRunStatus(
        readiness="development_run_complete",
        approval_eligible=False,
        input_manifest_path=validated.manifest_path,
        input_manifest_sha256=validated.manifest_sha256,
    )
