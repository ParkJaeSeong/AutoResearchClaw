"""Bundle contract tests: real files, no graph or experimental execution."""

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = (
    Path(__file__).resolve().parents[2]
    / "docs/research/2026-09-10-polymer-sdl/virtual-lab"
)
EXTRA = {
    "tasks": [
        "manufacturing_run_id",
        "block_id",
        "condition_level",
        "sequence_index",
        "started_at",
        "ended_at",
        "parent_task_id",
    ],
    "specimens": ["manufacturing_run_id"],
    "conditions": ["condition_id", "scope_type", "scope_id", "method_id"],
    "results": [
        "manufacturing_run_id",
        "condition_id",
        "parent_attempt_id",
        "raw_sha256",
    ],
}


def validate(path):
    assert importlib.util.find_spec("researchclaw.codex.lab_csv"), (
        "CSV validator not implemented"
    )
    from researchclaw.codex.lab_csv import validate_bundle

    return validate_bundle(path)


def read(path, name):
    with (path / (name + ".csv")).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write(path, name, headers, rows):
    with (path / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, headers)
        writer.writeheader()
        writer.writerows(rows)


def change(path, name, index, **values):
    headers, rows = read(path, name)
    rows[index].update(values)
    write(path, name, headers, rows)


@pytest.fixture
def bundle(tmp_path):
    shutil.copytree(EXAMPLES / "examples", tmp_path, dirs_exist_ok=True)
    return tmp_path


@pytest.fixture
def v2(bundle):
    for name, extras in EXTRA.items():
        headers, rows = read(bundle, name)
        for i, row in enumerate(rows):
            row.update(dict.fromkeys(extras, ""))
            row["schema_version"] = "2"
            if "manufacturing_run_id" in extras:
                row["manufacturing_run_id"] = "RUN-01"
            if name == "tasks":
                row.update(
                    started_at="2026-09-10T10:00:00Z", ended_at="2026-09-10T11:00:00Z"
                )
            if name == "conditions":
                row.update(
                    condition_id=f"C{i}", scope_type="task", scope_id=row["task_id"]
                )
        write(bundle, name, headers + extras, rows)
    # each result points to a condition on its own measurement task
    _, conditions = read(bundle, "conditions")
    for i, row in enumerate(read(bundle, "results")[1]):
        match = next(c for c in conditions if c["task_id"] == row["task_id"])
        change(bundle, "results", i, condition_id=match["condition_id"])
    return bundle


def test_v1_preserved_and_never_scientifically_approved(bundle):
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    report = validate(bundle)
    assert report["structural_valid"], report
    assert report["schema_version"] == "1"
    assert report["traceability_limitations"]
    assert report["scientific_usable"] is False and report["m1_ready"] is False
    assert {"material_specification", "measurement_method", "actual_equipment"} <= set(
        report["scientific_gates"]
    )
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}
    json.dumps(report, allow_nan=False)


def test_v2_and_raw_hash(v2):
    raw = v2 / "raw.csv"
    raw.write_text("force,displacement\n1,2\n")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    change(v2, "results", 0, raw_file="raw.csv", raw_sha256=digest)
    report = validate(v2)
    assert report["structural_valid"], report
    assert report["provenance"]["raw.csv"] == digest


@pytest.mark.parametrize(
    "name,values",
    [
        ("tasks", {"schema_version": "9"}),
        ("tasks", {"schema_version": "2"}),
        ("tasks", {"data_origin": ""}),
        ("tasks", {"data_origin": "real"}),
        ("tasks", {"plan_id": "OTHER"}),
        ("tasks", {"operator_id": ""}),
        ("specimens", {"manufacturing_batch_id": "wrong"}),
        ("results", {"value": ""}),
        ("results", {"value": "NaN"}),
        ("results", {"value": "Infinity"}),
        ("results", {"unit": "S/m"}),
        ("results", {"quality_status": "missing", "value": "0"}),
        ("results", {"supersedes_measurement_id": "DEMO-R01"}),
        ("results", {"supersedes_measurement_id": "DEMO-R02"}),
        ("results", {"raw_file": "../outside.csv"}),
        ("results", {"raw_file": "absent.csv"}),
    ],
)
def test_rejects_invalid_v1(bundle, name, values):
    change(bundle, name, 0, **values)
    assert not validate(bundle)["structural_valid"]


@pytest.mark.parametrize(
    "name,values",
    [
        ("results", {"manufacturing_run_id": "OTHER"}),
        ("results", {"condition_id": "C0"}),
        ("results", {"parent_attempt_id": "DEMO-A01"}),
        ("results", {"parent_attempt_id": "DEMO-A02"}),
        ("conditions", {"scope_type": "attempt", "scope_id": "absent"}),
        ("tasks", {"parent_task_id": "DEMO-T01"}),
    ],
)
def test_rejects_invalid_v2(v2, name, values):
    change(v2, name, 0, **values)
    assert not validate(v2)["structural_valid"]


def test_rejects_symlink_escape(bundle, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.csv")
    outside.write_text("private")
    (bundle / "linked.csv").symlink_to(outside)
    change(bundle, "results", 0, raw_file="linked.csv")
    report = validate(bundle)
    assert not report["structural_valid"]
    assert "linked.csv" not in report["provenance"]


@pytest.mark.parametrize("digest", ["", "0" * 64])
def test_rejects_missing_or_mismatched_hash(v2, digest):
    (v2 / "raw.csv").write_text("x")
    change(v2, "results", 0, raw_file="raw.csv", raw_sha256=digest)
    assert not validate(v2)["structural_valid"]


def test_header_only_template(tmp_path):
    shutil.copytree(EXAMPLES / "templates", tmp_path, dirs_exist_ok=True)
    report = validate(tmp_path)
    assert report["structural_valid"] and not report["has_data"]
    assert not report["m1_ready"] and not report["scientific_usable"]


def test_duplicate_conflicting_measurement(bundle):
    headers, rows = read(bundle, "results")
    rows.append(dict(rows[0], value="99"))
    write(bundle, "results", headers, rows)
    assert not validate(bundle)["structural_valid"]


def test_quality_missing_preserves_blank(bundle):
    change(bundle, "results", 0, quality_status="missing", value="")
    assert validate(bundle)["structural_valid"]
    assert read(bundle, "results")[1][0]["value"] == ""


def test_cli_exit_codes(bundle):
    assert importlib.util.find_spec("researchclaw.codex.lab_csv"), (
        "CSV validator not implemented"
    )
    args = [sys.executable, "-m", "researchclaw.codex.lab_csv", str(bundle)]
    good = subprocess.run(args, capture_output=True, text=True, check=False)
    assert good.returncode == 0 and json.loads(good.stdout)["structural_valid"]
    change(bundle, "results", 0, value="bad")
    bad = subprocess.run(args, capture_output=True, text=True, check=False)
    assert bad.returncode == 2 and not json.loads(bad.stdout)["structural_valid"]


def test_retry_and_correction_keep_original_rows(v2):
    headers, rows = read(v2, "results")
    rows.append(
        dict(
            rows[0],
            measurement_id="CORRECTED",
            value="0.00002",
            supersedes_measurement_id="DEMO-R01",
        )
    )
    rows.append(
        dict(
            rows[0],
            measurement_id="RETRY",
            attempt_id="RETRY-A",
            parent_attempt_id="DEMO-A01",
        )
    )
    write(v2, "results", headers, rows)
    report = validate(v2)
    assert report["structural_valid"], report
    assert report["row_counts"]["results"] == 4


def test_conflicting_metric_same_attempt_requires_correction(v2):
    headers, rows = read(v2, "results")
    rows.append(dict(rows[0], measurement_id="CONFLICT", value="99"))
    write(v2, "results", headers, rows)
    assert not validate(v2)["structural_valid"]


def test_retry_cycle(v2):
    headers, rows = read(v2, "results")
    rows[0]["parent_attempt_id"] = "RETRY-A"
    rows.append(
        dict(
            rows[0],
            measurement_id="RETRY",
            attempt_id="RETRY-A",
            parent_attempt_id="DEMO-A01",
        )
    )
    write(v2, "results", headers, rows)
    assert not validate(v2)["structural_valid"]


def test_correction_cycle(bundle):
    headers, rows = read(bundle, "results")
    rows[0]["supersedes_measurement_id"] = "CORRECTED"
    rows.append(
        dict(rows[0], measurement_id="CORRECTED", supersedes_measurement_id="DEMO-R01")
    )
    write(bundle, "results", headers, rows)
    assert not validate(bundle)["structural_valid"]


def test_missing_v2_column(v2):
    headers, rows = read(v2, "tasks")
    headers.remove("manufacturing_run_id")
    for row in rows:
        del row["manufacturing_run_id"]
    write(v2, "tasks", headers, rows)
    assert not validate(v2)["structural_valid"]


def test_real_planned_v2_can_leave_future_fields_empty(v2):
    for name, extra_columns in EXTRA.items():
        headers, rows = read(v2, name)
        for row in rows:
            row["data_origin"] = "real"
            if name == "tasks":
                row.update(status="planned", operator_id="")
                for key in extra_columns:
                    row[key] = ""
            if name == "specimens":
                row["manufacturing_run_id"] = ""
        write(v2, name, headers, [] if name == "results" else rows)
    assert validate(v2)["structural_valid"]


def test_arbitrary_long_notes_are_not_rejected(bundle):
    change(bundle, "tasks", 0, notes="x" * 150000)
    assert validate(bundle)["structural_valid"]


@pytest.mark.parametrize(
    "values",
    [
        {"started_at": "yesterday"},
        {"started_at": "2026-09-10T10:00:00"},
        {"started_at": "2026-09-10T10:00:00Z", "ended_at": "2026-09-10T09:00:00Z"},
        {"started_at": ""},
        {"ended_at": ""},
    ],
)
def test_v2_performed_timestamps(v2, values):
    change(v2, "tasks", 0, **values)
    assert not validate(v2)["structural_valid"]


def test_v2_completed_lineage_cannot_be_all_blank(v2):
    for name in ["tasks", "specimens", "results"]:
        headers, rows = read(v2, name)
        for row in rows:
            row["manufacturing_run_id"] = ""
        write(v2, name, headers, rows)
    assert not validate(v2)["structural_valid"]


def test_manufacturing_run_cannot_name_two_molding_tasks(v2):
    headers, rows = read(v2, "tasks")
    rows.append(dict(rows[1], task_id="SECOND-MOLD", output_batch_id="SECOND-BATCH"))
    write(v2, "tasks", headers, rows)
    assert not validate(v2)["structural_valid"]


def append_rework(v2, **overrides):
    headers, rows = read(v2, "tasks")
    rework = dict(
        rows[1],
        task_id="REWORK",
        output_batch_id="REWORK-BATCH",
        manufacturing_run_id="REWORK-RUN",
        parent_task_id=rows[1]["task_id"],
    )
    rework.update(overrides)
    rows.append(rework)
    write(v2, "tasks", headers, rows)


def test_manufacturing_rework_uses_fresh_run_and_batch(v2):
    append_rework(v2)
    report = validate(v2)
    assert report["structural_valid"], report


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_batch_id": "UNRELATED-MATERIAL"},
        {"manufacturing_run_id": "RUN-01"},
        {"output_batch_id": "DEMO-MOLDED-01"},
        {"operation": "extrusion"},
    ],
)
def test_rework_rejects_contrary_lineage(v2, overrides):
    append_rework(v2, **overrides)
    assert not validate(v2)["structural_valid"]


@pytest.mark.parametrize("field", ["block_id", "condition_level"])
def test_measurement_preserves_manufacturing_assignment(v2, field):
    change(v2, "tasks", 1, **{field: "ORIGINAL"})
    change(v2, "tasks", 2, **{field: "CHANGED"})
    change(v2, "tasks", 3, **{field: "ORIGINAL"})
    assert not validate(v2)["structural_valid"]


@pytest.mark.parametrize(
    "scope,scope_id",
    [
        ("task", "DEMO-T03"),
        ("specimen", "DEMO-EC-01"),
        ("attempt", "DEMO-A01"),
    ],
)
def test_all_applicable_conditions_must_use_result_method(v2, scope, scope_id):
    headers, rows = read(v2, "conditions")
    rows.append(
        dict(
            rows[2],
            condition_id="ADDITIONAL",
            scope_type=scope,
            scope_id=scope_id,
            method_id="DIFFERENT-METHOD",
        )
    )
    write(v2, "conditions", headers, rows)
    assert not validate(v2)["structural_valid"]
