import hashlib
import json

import pytest

from researchclaw.core import development_execution
from researchclaw.core.development_execution import run_development_experiment
from researchclaw.core.persistence import atomic_write_json
from tests.codex_native.helpers import (
    build_stage_twelve_project,
    write_runnable_development_fixture,
)


def test_run_writes_non_evidentiary_metrics_without_mutating_gate(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    resources_before = (project.root / "experiment/resources.json").read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    approvals_before = {
        path: path.read_bytes() for path in sorted((project.root / "approvals").glob("*.json"))
    }
    research_result = project.root / "experiment/results.json"
    research_result.write_bytes(b'{"research":"prior"}\n')

    status = run_development_experiment(
        project, "experiment/input_manifest.dev.json", max_seconds=120
    )

    result = json.loads((project.root / "experiment/dev_results.json").read_text())
    assert status.readiness == "development_run_complete"
    assert status.approval_eligible is False
    assert result["development_only"] is True
    assert result["evidence_eligible"] is False
    assert result["model"] == {
        "name": "ridge", "alpha": 1.0, "implementation": "numpy_closed_form"
    }
    assert (
        result["aggregate_metrics"]["rmse_cycles"]
        >= result["aggregate_metrics"]["mae_cycles"]
    )
    assert (project.root / "experiment/resources.json").read_bytes() == resources_before
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert {
        path: path.read_bytes() for path in sorted((project.root / "approvals").glob("*.json"))
    } == approvals_before
    assert research_result.read_bytes() == b'{"research":"prior"}\n'


def test_result_has_complete_schema_and_finite_runtime(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)

    run_development_experiment(
        project, "experiment/input_manifest.dev.json", max_seconds=17
    )

    result = json.loads((project.root / "experiment/dev_results.json").read_text())
    assert set(result) == {
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
    assert result["runtime"]["max_seconds"] == 17
    assert 0.0 <= result["runtime"]["elapsed_seconds"] <= 17.0


@pytest.mark.parametrize(
    ("column_name", "value_for_cell"),
    [
        ("cycle_life_cycles", lambda labels, cell_id: labels[cell_id]),
        ("split_role", lambda _labels, cell_id: "train" if cell_id <= "C03" else "test"),
        ("feature_cutoff_cycle", lambda _labels, _cell_id: "2"),
    ],
    ids=("label", "split-role", "cutoff-metadata"),
)
def test_run_rejects_label_and_split_metadata_feature_columns(
    tmp_path, column_name, value_for_cell
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    cell_lines = cells_path.read_text(encoding="utf-8").splitlines()
    labels = {line.split(",")[2]: line.split(",")[-1] for line in cell_lines[1:]}
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    feature_lines = features_path.read_text(encoding="utf-8").splitlines()
    changed = [feature_lines[0] + "," + column_name]
    for line in feature_lines[1:]:
        cell_id = line.split(",")[2]
        changed.append(line + "," + value_for_cell(labels, cell_id))
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/features.dev.csv",
        "features",
        "\n".join(changed) + "\n",
    )

    with pytest.raises(ValueError, match="feature_metadata_leakage"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")

    assert not (project.root / "experiment/dev_results.json").exists()


def test_finite_inputs_cannot_finalize_non_finite_numerical_results(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    lines = features_path.read_text(encoding="utf-8").splitlines()
    overflow_rows = [lines[0]]
    for line in lines[1:]:
        fields = line.split(",")
        fields[-2:] = ["1e308", "1e308"]
        overflow_rows.append(",".join(fields))
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/features.dev.csv",
        "features",
        "\n".join(overflow_rows) + "\n",
    )
    result_path = project.root / "experiment/dev_results.json"
    result_path.write_bytes(b'{"prior":true}\n')

    with pytest.raises(ValueError, match="numerical_error"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")

    assert result_path.read_bytes() == b'{"prior":true}\n'
    assert _execution_event(project)["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "numerical_error",
    }


def test_atomic_json_writer_rejects_non_standard_non_finite_values(tmp_path):
    destination = tmp_path / "strict.json"

    with pytest.raises(ValueError, match="Out of range float values"):
        atomic_write_json(destination, {"metric": float("nan")}, prefix="strict-")

    assert not destination.exists()


def test_success_atomically_replaces_an_existing_development_result(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    destination = project.root / "experiment/dev_results.json"
    destination.write_bytes(b'{"prior":true}\n')

    run_development_experiment(project, "experiment/input_manifest.dev.json")

    assert destination.read_bytes() != b'{"prior":true}\n'
    assert json.loads(destination.read_text())["development_only"] is True


def _write_csv_and_update_manifest(project, relative_path, payload_key, text):
    csv_path = project.root / relative_path
    csv_path.write_text(text, encoding="utf-8")
    manifest_path = project.root / "experiment/input_manifest.dev.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[payload_key]["sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")


def _execution_event(project):
    events = [
        json.loads(line)
        for line in (project.root / "evaluation/events.jsonl").read_text().splitlines()
    ]
    return events[-1]


def _write_hand_computable_split_fixture(
    project,
    *,
    validation_label: int,
    calibration_label: int,
    test_label: int,
):
    """Write one dataset whose train-only Ridge prediction is exactly 3.0."""
    write_runnable_development_fixture(project)
    cells = (
        "dataset_id,condition_id,cell_id,split_role,feature_cutoff_cycle,cycle_life_cycles\n"
        "HAND,G01,C01,train,1,2\n"
        "HAND,G02,C02,train,1,4\n"
        f"HAND,G03,C03,validation,1,{validation_label}\n"
        f"HAND,G04,C04,calibration,1,{calibration_label}\n"
        f"HAND,G05,C05,test,1,{test_label}\n"
    )
    features = (
        "dataset_id,condition_id,cell_id,cycle_index,capacity_ah\n"
        "HAND,G01,C01,1,0.0\n"
        "HAND,G02,C02,1,1.0\n"
        "HAND,G03,C03,1,0.25\n"
        "HAND,G04,C04,1,0.75\n"
        "HAND,G05,C05,1,0.5\n"
    )
    manifest_path = project.root / "experiment/input_manifest.dev.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["datasets"] = [{"dataset_id": "HAND"}]
    for relative_path, payload_key, text in (
        ("experiment/dev_data/cells.dev.csv", "cell_records", cells),
        ("experiment/dev_data/features.dev.csv", "features", features),
    ):
        path = project.root / relative_path
        path.write_text(text, encoding="utf-8")
        manifest[payload_key]["row_count"] = 5
        manifest[payload_key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_timeout_preserves_existing_result_and_records_sanitized_failure(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    result = project.root / "experiment/dev_results.json"
    result.write_bytes(b'{"prior":true}\n')
    ticks = iter([0.0, 0.1, 2.0])

    with pytest.raises(ValueError, match="development_timeout"):
        run_development_experiment(
            project,
            "experiment/input_manifest.dev.json",
            max_seconds=1,
            clock=lambda: next(ticks),
        )

    assert result.read_bytes() == b'{"prior":true}\n'
    event = _execution_event(project)
    assert event["type"] == "development_execution_failed"
    assert event["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "development_timeout",
    }


def test_timeout_during_result_staging_preserves_prior_result(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    result = project.root / "experiment/dev_results.json"
    result.write_bytes(b'{"prior":true}\n')
    ticks = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 2.0])

    with pytest.raises(ValueError, match="development_timeout"):
        run_development_experiment(
            project,
            "experiment/input_manifest.dev.json",
            max_seconds=1,
            clock=lambda: next(ticks),
        )

    assert result.read_bytes() == b'{"prior":true}\n'
    events = [
        json.loads(line)
        for line in (project.root / "evaluation/events.jsonl").read_text().splitlines()
    ]
    matching = [event for event in events if event["type"] == "development_execution_failed"]
    assert len(matching) == 1
    assert matching[0]["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "development_timeout",
    }


def test_result_and_event_use_final_deadline_observation(tmp_path, monkeypatch):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    now = [0.0]
    original_stage = development_execution._stage_result_json

    def stage_after_time_advances(destination, payload):
        now[0] = 5.0
        return original_stage(destination, payload)

    monkeypatch.setattr(
        development_execution, "_stage_result_json", stage_after_time_advances
    )

    run_development_experiment(
        project,
        "experiment/input_manifest.dev.json",
        max_seconds=10,
        clock=lambda: now[0],
    )

    result = json.loads(
        (project.root / "experiment/dev_results.json").read_text(encoding="utf-8")
    )
    event = _execution_event(project)
    assert result["runtime"]["elapsed_seconds"] == 5.0
    assert event["payload"]["elapsed_seconds"] == 5.0


def test_completion_event_contains_only_finalized_artifact_metadata(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    ticks = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])

    run_development_experiment(
        project,
        "experiment/input_manifest.dev.json",
        max_seconds=1,
        clock=lambda: next(ticks),
    )

    result_path = project.root / "experiment/dev_results.json"
    event = _execution_event(project)
    assert event["type"] == "development_execution_completed"
    assert event["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "result_path": "experiment/dev_results.json",
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "elapsed_seconds": 0.6,
        "dataset_count": 1,
        "cell_count": 8,
    }


def test_failure_event_never_includes_rows_labels_predictions_or_exception_text(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    feature_text = features_path.read_text(encoding="utf-8").replace(
        "SYNTH_DEV,G01,C01,1,2.01,41.0",
        "SYNTH_DEV,G01,C01,1,not-a-number,41.0",
    )
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/features.dev.csv",
        "features",
        feature_text,
    )

    with pytest.raises(ValueError, match="invalid_numeric_value"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")

    event = _execution_event(project)
    assert event["type"] == "development_execution_failed"
    assert event["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "invalid_numeric_value",
    }


@pytest.mark.parametrize(
    "failure_kind",
    ("invalid-json", "referenced-hash-mismatch", "duplicate-cell"),
)
def test_early_validation_failure_event_includes_available_manifest_identity(
    tmp_path, failure_kind
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest_path = write_runnable_development_fixture(project)
    if failure_kind == "invalid-json":
        manifest_path.write_bytes(b'{"broken":')
    elif failure_kind == "referenced-hash-mismatch":
        features = project.root / "experiment/dev_data/features.dev.csv"
        features.write_bytes(features.read_bytes() + b"\n")
    else:
        cells = project.root / "experiment/dev_data/cells.dev.csv"
        lines = cells.read_text(encoding="utf-8").splitlines()
        duplicate = "\n".join([*lines, lines[1]]) + "\n"
        _write_csv_and_update_manifest(
            project,
            "experiment/dev_data/cells.dev.csv",
            "cell_records",
            duplicate,
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["cell_records"]["row_count"] += 1
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    expected_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError):
        run_development_experiment(project, "experiment/input_manifest.dev.json")

    assert _execution_event(project)["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": expected_digest,
        "error_category": "development_input_validation_failed",
    }


@pytest.mark.parametrize("max_seconds", (0, -1, 1.5, True))
def test_run_requires_a_positive_integer_deadline(tmp_path, max_seconds):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)

    with pytest.raises(ValueError, match="invalid_max_seconds"):
        run_development_experiment(
            project,
            "experiment/input_manifest.dev.json",
            max_seconds=max_seconds,
        )


def test_only_train_labels_fit_ridge_and_metrics_use_test_rows(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    _write_hand_computable_split_fixture(
        project, validation_label=100, calibration_label=200, test_label=8
    )

    run_development_experiment(project, "experiment/input_manifest.dev.json")
    baseline = json.loads((project.root / "experiment/dev_results.json").read_text())
    assert baseline["aggregate_metrics"] == {
        "mae_cycles": pytest.approx(5.0),
        "rmse_cycles": pytest.approx(5.0),
    }

    _write_hand_computable_split_fixture(
        project, validation_label=500, calibration_label=600, test_label=8
    )
    run_development_experiment(project, "experiment/input_manifest.dev.json")
    held_out_label_mutation = json.loads(
        (project.root / "experiment/dev_results.json").read_text()
    )
    assert held_out_label_mutation["aggregate_metrics"] == {
        "mae_cycles": pytest.approx(5.0),
        "rmse_cycles": pytest.approx(5.0),
    }

    _write_hand_computable_split_fixture(
        project, validation_label=500, calibration_label=600, test_label=10
    )
    run_development_experiment(project, "experiment/input_manifest.dev.json")
    test_label_mutation = json.loads(
        (project.root / "experiment/dev_results.json").read_text()
    )
    assert test_label_mutation["aggregate_metrics"] == {
        "mae_cycles": pytest.approx(7.0),
        "rmse_cycles": pytest.approx(7.0),
    }


@pytest.mark.parametrize("value", ("", "not-a-number", "nan", "inf"))
def test_run_rejects_non_finite_or_non_numeric_predictors(tmp_path, value):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    feature_text = features_path.read_text(encoding="utf-8").replace(
        "SYNTH_DEV,G01,C01,1,2.01,41.0",
        f"SYNTH_DEV,G01,C01,1,{value},41.0",
    )
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/features.dev.csv",
        "features",
        feature_text,
    )

    with pytest.raises(ValueError, match="invalid_numeric_value"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")


def test_run_rejects_unknown_split_role(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    cell_text = cells_path.read_text(encoding="utf-8").replace(
        "SYNTH_DEV,G02,C03,train,2,7",
        "SYNTH_DEV,G02,C03,unknown,2,7",
    )
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/cells.dev.csv",
        "cell_records",
        cell_text,
    )

    with pytest.raises(ValueError, match="invalid_split_role"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")


def test_run_requires_a_test_cell_per_dataset(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    cell_text = cells_path.read_text(encoding="utf-8").replace(",test,2,", ",train,2,")
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/cells.dev.csv",
        "cell_records",
        cell_text,
    )

    with pytest.raises(ValueError, match="missing_test_cells"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")


def test_run_requires_a_train_cell_per_dataset(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    cell_text = cells_path.read_text(encoding="utf-8").replace(",train,2,", ",test,2,")
    _write_csv_and_update_manifest(
        project,
        "experiment/dev_data/cells.dev.csv",
        "cell_records",
        cell_text,
    )

    with pytest.raises(ValueError, match="missing_train_cells"):
        run_development_experiment(project, "experiment/input_manifest.dev.json")


@pytest.mark.parametrize(
    ("failure_kind", "expected_message"),
    [
        ("duplicate-cell", "cell_id is duplicated"),
        ("duplicate-cycle", "cell-cycle is duplicated"),
        ("group-leakage", "condition group crosses split roles"),
        ("post-cutoff", "feature cutoff violated"),
        ("unknown-cell", "unknown cell_id"),
        ("mismatched-keys", "feature keys disagree"),
        ("missing-label", "cutoff and label must be integers"),
        ("nan-label", "cutoff and label must be integers"),
        ("infinite-label", "cutoff and label must be integers"),
    ],
)
def test_run_rejects_structural_and_label_safety_violations(
    tmp_path, failure_kind, expected_message
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    manifest_path = project.root / "experiment/input_manifest.dev.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    cell_lines = cells_path.read_text(encoding="utf-8").splitlines()
    feature_lines = features_path.read_text(encoding="utf-8").splitlines()

    if failure_kind == "duplicate-cell":
        cell_lines.append(cell_lines[1])
    elif failure_kind == "duplicate-cycle":
        feature_lines.append(feature_lines[1])
    elif failure_kind == "group-leakage":
        cell_lines[2] = cell_lines[2].replace(",train,", ",test,")
    elif failure_kind == "post-cutoff":
        feature_lines[1] = feature_lines[1].replace(",1,2.01,", ",3,2.01,")
    elif failure_kind == "unknown-cell":
        feature_lines[1] = feature_lines[1].replace(",C01,", ",UNKNOWN,")
    elif failure_kind == "mismatched-keys":
        feature_lines[1] = feature_lines[1].replace("SYNTH_DEV,G01", "OTHER,G01")
    else:
        replacement = {"missing-label": "", "nan-label": "nan", "infinite-label": "inf"}[
            failure_kind
        ]
        fields = cell_lines[1].split(",")
        fields[-1] = replacement
        cell_lines[1] = ",".join(fields)

    cells_path.write_text("\n".join(cell_lines) + "\n", encoding="utf-8")
    features_path.write_text("\n".join(feature_lines) + "\n", encoding="utf-8")
    manifest["cell_records"].update(
        {
            "row_count": len(cell_lines) - 1,
            "sha256": hashlib.sha256(cells_path.read_bytes()).hexdigest(),
        }
    )
    manifest["features"].update(
        {
            "row_count": len(feature_lines) - 1,
            "sha256": hashlib.sha256(features_path.read_bytes()).hexdigest(),
        }
    )
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        run_development_experiment(project, "experiment/input_manifest.dev.json")

    assert not (project.root / "experiment/dev_results.json").exists()


def test_run_rejects_manifest_project_path_escape(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )

    with pytest.raises(ValueError, match="project-relative"):
        run_development_experiment(project, "../outside.json")

    assert not (project.root / "experiment/dev_results.json").exists()


@pytest.mark.parametrize(
    "failure_family", ("validation", "numerical", "timeout", "numpy-unavailable")
)
def test_every_failure_family_preserves_durable_control_bytes(
    tmp_path, monkeypatch, failure_family
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest_path = write_runnable_development_fixture(project)
    clock = None
    if failure_family == "validation":
        manifest_path.write_bytes(b'{"broken":')
    elif failure_family == "numerical":
        features_path = project.root / "experiment/dev_data/features.dev.csv"
        lines = features_path.read_text(encoding="utf-8").splitlines()
        for index in range(1, len(lines)):
            fields = lines[index].split(",")
            fields[-2:] = ["1e308", "1e308"]
            lines[index] = ",".join(fields)
        _write_csv_and_update_manifest(
            project,
            "experiment/dev_data/features.dev.csv",
            "features",
            "\n".join(lines) + "\n",
        )
    elif failure_family == "timeout":
        ticks = iter([0.0, 0.1, 2.0])

        def clock():
            return next(ticks)
    else:
        real_import = development_execution.importlib.import_module

        def blocked_import(name):
            if name == "numpy":
                raise ImportError("blocked for regression")
            return real_import(name)

        monkeypatch.setattr(
            development_execution.importlib, "import_module", blocked_import
        )
    research_result = project.root / "experiment/results.json"
    research_result.write_bytes(b'{"research":"prior"}\n')
    development_result = project.root / "experiment/dev_results.json"
    development_result.write_bytes(b'{"development":"prior"}\n')
    state_path = project.root / ".researchclaw/state.json"
    resources_path = project.root / "experiment/resources.json"
    approvals = sorted((project.root / "approvals").glob("*.json"))
    controls_before = {
        "state": state_path.read_bytes(),
        "resources": resources_path.read_bytes(),
        "approvals": {path: path.read_bytes() for path in approvals},
        "research_result": research_result.read_bytes(),
        "development_result": development_result.read_bytes(),
    }
    arguments = {}
    if clock is not None:
        arguments["clock"] = clock
        arguments["max_seconds"] = 1

    with pytest.raises(ValueError):
        run_development_experiment(
            project, "experiment/input_manifest.dev.json", **arguments
        )

    assert state_path.read_bytes() == controls_before["state"]
    assert resources_path.read_bytes() == controls_before["resources"]
    assert {path: path.read_bytes() for path in approvals} == controls_before["approvals"]
    assert research_result.read_bytes() == controls_before["research_result"]
    assert development_result.read_bytes() == controls_before["development_result"]
