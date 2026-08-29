import hashlib
import json

import pytest

from researchclaw.core.development_execution import run_development_experiment
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
    assert not (project.root / "experiment/results.json").exists()


def _write_csv_and_update_manifest(project, relative_path, payload_key, text):
    csv_path = project.root / relative_path
    csv_path.write_text(text, encoding="utf-8")
    manifest_path = project.root / "experiment/input_manifest.dev.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[payload_key]["sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")


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
