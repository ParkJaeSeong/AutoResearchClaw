"""The user-facing sample must calculate results from its declared rows."""

import csv
import json
from pathlib import Path
import subprocess
import sys


SAMPLE = Path(__file__).resolve().parents[2] / "examples/stage13-coherent-synthetic"


def test_sample_metric_and_partitions_are_reconstructible(tmp_path):
    scenario = json.loads((SAMPLE / "scenario.json").read_text())
    done = subprocess.run(
        [sys.executable, str(SAMPLE / "baseline.py"), str(SAMPLE / "input.csv")],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(done.stdout)
    assert result["synthetic_only"] is True
    assert result["evidence_eligible"] is False
    assert result["metric"] == {"name": "mae_cycles", "unit": "cycles", "value": 0.5}
    assert scenario["metric"]["name"] == result["metric"]["name"]
    assert scenario["metric"]["unit"] == result["metric"]["unit"]
    assert result["rows"] == 14
    assert result["split_summary"] == {
        "train": {"cell_count": 6, "group_count": 3},
        "validation": {"cell_count": 2, "group_count": 1},
        "calibration": {"cell_count": 2, "group_count": 1},
        "test": {"cell_count": 4, "group_count": 2},
    }
    # Alter only held-out predictions: a hard-coded result must fail this test.
    with (SAMPLE / "input.csv").open() as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["split"] == "test":
            row["prediction_cycles"] = row["target_cycles"]
    changed = tmp_path / "changed.csv"
    with changed.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    changed_result = subprocess.run(
        [sys.executable, str(SAMPLE / "baseline.py"), str(changed)],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(changed_result.stdout)["metric"]["value"] == 0.0


def test_sample_rejects_cross_split_group_leakage(tmp_path):
    data = (SAMPLE / "input.csv").read_text().replace("c11,g6,test", "c11,g1,test")
    path = tmp_path / "leak.csv"
    path.write_text(data)
    result = subprocess.run(
        [sys.executable, str(SAMPLE / "baseline.py"), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "group crosses splits" in result.stderr
