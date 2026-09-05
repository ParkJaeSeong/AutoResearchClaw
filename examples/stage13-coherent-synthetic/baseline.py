"""Read-only arithmetic check for a synthetic source bundle, not a stage runner."""

import argparse
import csv
import json
import math
from pathlib import Path


def evaluate(path: Path) -> dict:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [
            "cell_id", "group_id", "split", "target_cycles", "prediction_cycles"
        ]:
            raise ValueError("unexpected CSV columns")
        rows = list(reader)
    counts = {role: set() for role in ("train", "validation", "calibration", "test")}
    groups = {role: set() for role in counts}
    seen_cells = set()
    group_roles = {}
    errors = []
    for row in rows:
        cell, group, role = row["cell_id"], row["group_id"], row["split"]
        if not cell or not group or role not in counts:
            raise ValueError("missing identity or unknown split")
        if cell in seen_cells:
            raise ValueError("duplicate cell")
        if group in group_roles and group_roles[group] != role:
            raise ValueError("group crosses splits")
        seen_cells.add(cell)
        group_roles[group] = role
        counts[role].add(cell)
        groups[role].add(group)
        target, prediction = float(row["target_cycles"]), float(row["prediction_cycles"])
        if not math.isfinite(target) or not math.isfinite(prediction):
            raise ValueError("nonfinite measurement")
        if role == "test":
            errors.append(abs(target - prediction))
    if any(not cells for cells in counts.values()):
        raise ValueError("every declared split needs rows")
    return {
        "synthetic_only": True,
        "evidence_eligible": False,
        "rows": len(rows),
        "metric": {"name": "mae_cycles", "unit": "cycles", "value": sum(errors) / len(errors)},
        "split_summary": {
            role: {"cell_count": len(counts[role]), "group_count": len(groups[role])}
            for role in counts
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input), sort_keys=True, allow_nan=False))
