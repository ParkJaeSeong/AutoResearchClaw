"""Read-only Pilot virtual-lab CSV bundle validation.

Run ``python -m researchclaw.codex.lab_csv PATH`` for a JSON report (exit 0
structurally valid, 2 invalid). PATH contains tasks.csv, specimens.csv,
conditions.csv and results.csv, plus optional relative raw files. Versions 1
and additive 2 are accepted without migration. Header-only files are templates;
their declared version is unknown. Validation never registers graph records,
approves scientific use, or declares M1 ready. Material specifications, method
suitability and actual equipment must be assessed outside this file contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from pathlib import Path, PureWindowsPath

BASE = {
    "tasks": [
        "schema_version",
        "data_origin",
        "plan_id",
        "task_id",
        "operation",
        "equipment_id",
        "input_batch_id",
        "output_batch_id",
        "specimen_id",
        "status",
        "operator_id",
        "notes",
    ],
    "specimens": [
        "schema_version",
        "data_origin",
        "specimen_id",
        "manufacturing_batch_id",
        "intended_test",
        "sampling_location",
        "notes",
    ],
    "conditions": [
        "schema_version",
        "data_origin",
        "task_id",
        "parameter",
        "planned_value",
        "actual_value",
        "unit",
        "value_status",
        "notes",
    ],
    "results": [
        "schema_version",
        "data_origin",
        "measurement_id",
        "task_id",
        "specimen_id",
        "attempt_id",
        "metric",
        "value",
        "unit",
        "quality_status",
        "method_id",
        "direction",
        "contact_cycle_id",
        "raw_file",
        "supersedes_measurement_id",
        "notes",
    ],
}
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
UNITS = {"electrical_conductivity": "S/cm", "tensile_strength": "MPa"}


def validate_bundle(path: Path) -> dict:
    """Return diagnostics and hashes without modifying any submitted bytes."""
    root = Path(path).resolve()
    errors: list[dict] = []
    provenance: dict[str, str] = {}
    tables: dict[str, list[dict]] = {}
    headers: dict[str, list[str]] = {}

    def error(table, row, code, detail):
        errors.append(
            {"file": table + ".csv", "row": row, "code": code, "detail": detail}
        )

    def safe_file(relative):
        p = Path(relative)
        if (
            p.is_absolute()
            or PureWindowsPath(relative).is_absolute()
            or "\\" in relative
        ):
            raise ValueError("must be a portable relative path")
        target = (root / p).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("path escapes bundle or is not a regular file")
        return target

    for name in BASE:
        tables[name], headers[name] = [], []
        previous_field_limit = csv.field_size_limit()
        try:
            raw = safe_file(name + ".csv").read_bytes()
            csv.field_size_limit(max(previous_field_limit, len(raw)))
            provenance[name + ".csv"] = hashlib.sha256(raw).hexdigest()
            reader = csv.DictReader(
                io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True
            )
            headers[name] = reader.fieldnames or []
            if len(set(headers[name])) != len(headers[name]):
                error(name, 1, "duplicate_header", "column names must be unique")
            for number, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    error(name, number, "row_width", "row width differs from header")
                tables[name].append(
                    {
                        key: (value or "").strip()
                        for key, value in row.items()
                        if key is not None
                    }
                )
        except (OSError, ValueError, csv.Error, RuntimeError) as exc:
            error(name, None, "read_error", str(exc))
        finally:
            csv.field_size_limit(previous_field_limit)

    versions, origins, plans = set(), set(), set()
    for name, rows in tables.items():
        for number, row in enumerate(rows, 2):
            version, origin = row.get("schema_version", ""), row.get("data_origin", "")
            versions.add(version)
            origins.add(origin)
            if version not in {"1", "2"}:
                error(name, number, "schema_version", "schema_version must be 1 or 2")
            if origin not in {"synthetic", "real"}:
                error(
                    name, number, "data_origin", "data_origin must be synthetic or real"
                )
            if name == "tasks":
                plans.add(row.get("plan_id", ""))
    if len(versions) > 1:
        error(
            "tasks", None, "mixed_versions", "one version is required across all rows"
        )
    if len(origins) > 1:
        error("tasks", None, "mixed_origins", "synthetic and real rows cannot be mixed")
    if len(plans) > 1 or "" in plans:
        error("tasks", None, "plan_id", "tasks must name one nonempty plan_id")
    version = next(iter(versions)) if len(versions) == 1 else None
    for name, base_columns in BASE.items():
        required = base_columns + (EXTRA[name] if version == "2" else [])
        missing = sorted(set(required) - set(headers[name]))
        if missing:
            error(name, 1, "missing_columns", ", ".join(missing))
        # Never silently interpret populated v2 linkage as a v1 upgrade.
        if version == "1" and any(
            row.get(key) for row in tables[name] for key in EXTRA[name]
        ):
            error(
                name,
                None,
                "version_linkage_conflict",
                "v2 linkage values require declared version 2",
            )

    def required_values(name, row, number, keys):
        for key in keys:
            if not row.get(key):
                error(name, number, "missing_value", key)

    def index(name, key):
        result = {}
        for number, row in enumerate(tables[name], 2):
            value = row.get(key, "")
            if not value:
                error(name, number, "missing_id", key)
            elif value in result:
                error(
                    name,
                    number,
                    "duplicate_id",
                    f"{key}={value}; original rows are not overwritten",
                )
            else:
                result[value] = row
        return result

    tasks = index("tasks", "task_id")
    specimens = index("specimens", "specimen_id")
    measurements = index("results", "measurement_id")
    conditions = index("conditions", "condition_id") if version == "2" else {}
    batches = {}
    manufacturing_runs = {}
    for number, row in enumerate(tables["tasks"], 2):
        required_values("tasks", row, number, ["operation", "equipment_id", "status"])
        if row.get("status") not in {
            "planned",
            "in_progress",
            "completed",
            "failed",
            "cancelled",
        }:
            error("tasks", number, "status", "unknown task status")
        if row.get("status") in {"completed", "in_progress", "failed"} and not row.get(
            "operator_id"
        ):
            error("tasks", number, "operator_id", "performed work requires an operator")
        if version == "2":
            performed = row.get("status") in {"in_progress", "completed", "failed"}
            if performed:
                required_values("tasks", row, number, ["started_at"])
                if row.get("operation") == "injection_molding" or row.get(
                    "specimen_id"
                ):
                    required_values("tasks", row, number, ["manufacturing_run_id"])
            if row.get("status") in {"completed", "failed"}:
                required_values("tasks", row, number, ["ended_at"])
            timestamps = {}
            for key in ["started_at", "ended_at"]:
                if row.get(key):
                    try:
                        parsed = datetime.fromisoformat(row[key])
                        if parsed.tzinfo is None or parsed.utcoffset() is None:
                            raise ValueError("timezone required")
                        timestamps[key] = parsed
                    except ValueError:
                        error(
                            "tasks",
                            number,
                            "timestamp",
                            key + " requires ISO datetime with timezone",
                        )
            if "ended_at" in timestamps and "started_at" not in timestamps:
                error("tasks", number, "timestamp", "ended_at requires started_at")
            if (
                len(timestamps) == 2
                and timestamps["ended_at"] < timestamps["started_at"]
            ):
                error("tasks", number, "timestamp", "ended_at precedes started_at")
            run = row.get("manufacturing_run_id")
            if row.get("operation") == "injection_molding" and run:
                if run in manufacturing_runs:
                    error(
                        "tasks",
                        number,
                        "manufacturing_run_conflict",
                        "one run cannot identify multiple molding tasks",
                    )
                manufacturing_runs[run] = row
        batch = row.get("output_batch_id")
        if batch:
            if batch in batches:
                error("tasks", number, "duplicate_batch", batch)
            batches[batch] = row
        if row.get("sequence_index"):
            try:
                if int(row["sequence_index"]) < 0:
                    raise ValueError()
            except ValueError:
                error(
                    "tasks", number, "sequence_index", "must be a nonnegative integer"
                )

    def same(name, number, left, right, keys):
        for key in keys:
            if left.get(key, "") != right.get(key, ""):
                error(name, number, "incompatible_reference", key)

    for number, row in enumerate(tables["specimens"], 2):
        producer = batches.get(row.get("manufacturing_batch_id"))
        if not producer:
            error(
                "specimens",
                number,
                "batch_reference",
                "manufacturing batch has no producing task",
            )
        elif version == "2":
            same("specimens", number, row, producer, ["manufacturing_run_id"])
    for number, row in enumerate(tables["tasks"], 2):
        if row.get("specimen_id"):
            specimen = specimens.get(row["specimen_id"])
            if not specimen:
                error("tasks", number, "specimen_reference", row["specimen_id"])
            else:
                if row.get("input_batch_id") != specimen.get("manufacturing_batch_id"):
                    error(
                        "tasks",
                        number,
                        "batch_reference",
                        "task input must equal specimen manufacturing batch",
                    )
                if version == "2":
                    same("tasks", number, row, specimen, ["manufacturing_run_id"])
                    producer = batches.get(specimen.get("manufacturing_batch_id"))
                    if producer:
                        same(
                            "tasks",
                            number,
                            row,
                            producer,
                            ["block_id", "condition_level"],
                        )

    attempts = {}
    for number, row in enumerate(tables["results"], 2):
        required_values(
            "results",
            row,
            number,
            [
                "task_id",
                "specimen_id",
                "attempt_id",
                "metric",
                "unit",
                "quality_status",
            ],
        )
        task, specimen = (
            tasks.get(row.get("task_id")),
            specimens.get(row.get("specimen_id")),
        )
        if not task or not specimen:
            error("results", number, "result_reference", "unknown task or specimen")
        else:
            same("results", number, row, task, ["specimen_id"])
            if task.get("input_batch_id") != specimen.get("manufacturing_batch_id"):
                error(
                    "results",
                    number,
                    "batch_reference",
                    "result task and specimen batch differ",
                )
            if version == "2":
                required_values(
                    "results", row, number, ["manufacturing_run_id", "condition_id"]
                )
                same("results", number, row, task, ["manufacturing_run_id"])
                same("results", number, row, specimen, ["manufacturing_run_id"])
        attempt = row.get("attempt_id")
        if attempt in attempts:
            same(
                "results",
                number,
                row,
                attempts[attempt],
                ["task_id", "specimen_id", "manufacturing_run_id", "parent_attempt_id"],
            )
        elif attempt:
            attempts[attempt] = row
        quality, value = row.get("quality_status"), row.get("value", "")
        if quality not in {"unverified", "valid", "below_limit", "invalid", "missing"}:
            error("results", number, "quality_status", "unknown quality status")
        if quality in {"valid", "unverified"} and not value:
            error(
                "results",
                number,
                "missing_value",
                "numeric result required for valid/unverified",
            )
        if quality in {"missing", "below_limit"} and value:
            error(
                "results",
                number,
                "censored_value",
                "missing/below_limit must retain blank value",
            )
        if value:
            try:
                if not math.isfinite(float(value)):
                    raise ValueError()
            except ValueError:
                error(
                    "results", number, "numeric_value", "result must be a finite number"
                )
        if row.get("metric") in UNITS and row.get("unit") != UNITS[row["metric"]]:
            error(
                "results",
                number,
                "metric_unit",
                f"{row['metric']} requires {UNITS[row['metric']]}",
            )
        raw_file, digest = row.get("raw_file"), row.get("raw_sha256", "")
        if raw_file:
            try:
                target = safe_file(raw_file)
                with target.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                provenance[raw_file] = actual
                if (version == "2" or digest) and digest.lower() != actual:
                    error(
                        "results",
                        number,
                        "raw_sha256",
                        "missing or mismatched declared SHA-256",
                    )
            except (OSError, ValueError, RuntimeError) as exc:
                error("results", number, "raw_file", str(exc))
        elif digest:
            error("results", number, "raw_sha256", "hash has no raw_file")

    for number, row in enumerate(tables["conditions"], 2):
        required_values(
            "conditions", row, number, ["task_id", "parameter", "value_status"]
        )
        if row.get("task_id") not in tasks:
            error("conditions", number, "task_reference", "unknown task")
        if row.get("value_status") not in {"provided", "unknown", "not_applicable"}:
            error("conditions", number, "value_status", "unknown value status")
        if row.get("value_status") == "provided" and not (
            row.get("actual_value") or row.get("planned_value")
        ):
            error(
                "conditions", number, "missing_value", "provided condition has no value"
            )
        # Conditions may contain categorical values (M0/P0); numeric-looking
        # values must nevertheless be finite. Units and method completeness
        # remain scientific gates, not guessed numeric schemas.
        for key in ["planned_value", "actual_value"]:
            try:
                number_value = float(row.get(key, ""))
            except ValueError:
                continue
            if not math.isfinite(number_value):
                error("conditions", number, "numeric_value", key + " is nonfinite")
        if version == "2":
            scope = row.get("scope_type")
            target = {"task": tasks, "specimen": specimens, "attempt": attempts}.get(
                scope, {}
            ).get(row.get("scope_id"))
            if not target:
                error(
                    "conditions",
                    number,
                    "condition_scope",
                    "unknown scope type or target",
                )
            elif scope in {"task", "attempt"}:
                same("conditions", number, row, target, ["task_id"])
            elif tasks.get(row.get("task_id"), {}).get("specimen_id") != row.get(
                "scope_id"
            ):
                error(
                    "conditions",
                    number,
                    "condition_scope",
                    "specimen is not attached to condition task",
                )
    if version == "2":
        for number, row in enumerate(tables["results"], 2):
            condition = conditions.get(row.get("condition_id"))
            if not condition:
                error("results", number, "condition_reference", "unknown condition_id")
                continue
            same("results", number, row, condition, ["task_id"])
            expected = {
                "task": row.get("task_id"),
                "specimen": row.get("specimen_id"),
                "attempt": row.get("attempt_id"),
            }.get(condition.get("scope_type"))
            if not expected or expected != condition.get("scope_id"):
                error(
                    "results",
                    number,
                    "condition_scope",
                    "condition does not apply to this result",
                )
            if condition.get("method_id") and condition["method_id"] != row.get(
                "method_id"
            ):
                error(
                    "results",
                    number,
                    "condition_method",
                    "condition and result methods differ",
                )

    if version == "2":
        for number, row in enumerate(tables["results"], 2):
            scopes = {
                "task": row.get("task_id"),
                "specimen": row.get("specimen_id"),
                "attempt": row.get("attempt_id"),
            }
            for condition in conditions.values():
                if condition.get("scope_id") != scopes.get(condition.get("scope_type")):
                    continue
                if condition.get("task_id") != row.get("task_id"):
                    continue
                if condition.get("method_id") and condition["method_id"] != row.get(
                    "method_id"
                ):
                    error(
                        "results",
                        number,
                        "condition_method",
                        f"applicable condition {condition['condition_id']} and result methods differ",
                    )

    def links(name, records, field, identity, compatible):
        for key, row in records.items():
            parent = row.get(field)
            if not parent:
                continue
            target = records.get(parent)
            if not target or key == parent:
                error(
                    name, None, "parent_reference", f"{identity}={key}: invalid {field}"
                )
                continue
            same(name, None, row, target, compatible)
            if field == "parent_task_id":
                same(
                    name,
                    None,
                    row,
                    target,
                    ["input_batch_id", "block_id", "condition_level"],
                )
                if row.get("output_batch_id") or target.get("output_batch_id"):
                    for fresh_key in ["output_batch_id", "manufacturing_run_id"]:
                        if not row.get(fresh_key) or row.get(fresh_key) == target.get(
                            fresh_key
                        ):
                            error(
                                name,
                                None,
                                "rework_lineage",
                                f"manufacturing rework requires fresh {fresh_key}",
                            )
                else:
                    same(name, None, row, target, ["manufacturing_run_id"])

            visited = {key}
            cursor = parent
            while cursor in records:
                if cursor in visited:
                    error(name, None, "reference_cycle", f"{field} cycle at {cursor}")
                    break
                visited.add(cursor)
                cursor = records[cursor].get(field)

    metric_groups = {}
    for row in measurements.values():
        key = (row.get("attempt_id"), row.get("metric"))
        metric_groups.setdefault(key, []).append(row)
    for key, rows in metric_groups.items():
        if len(rows) < 2:
            continue
        ids = {row["measurement_id"] for row in rows}
        replaced = [
            row.get("supersedes_measurement_id")
            for row in rows
            if row.get("supersedes_measurement_id") in ids
        ]
        roots = [row for row in rows if not row.get("supersedes_measurement_id")]
        if (
            len(roots) != 1
            or len(replaced) != len(rows) - 1
            or len(set(replaced)) != len(replaced)
        ):
            error(
                "results",
                None,
                "metric_conflict",
                f"{key}: repeated metric requires one unbranched correction chain",
            )

    links(
        "tasks",
        tasks,
        "parent_task_id",
        "task_id",
        ["plan_id", "operation", "specimen_id"],
    )
    links(
        "results",
        attempts,
        "parent_attempt_id",
        "attempt_id",
        ["task_id", "specimen_id", "manufacturing_run_id"],
    )
    links(
        "results",
        measurements,
        "supersedes_measurement_id",
        "measurement_id",
        [
            "task_id",
            "specimen_id",
            "attempt_id",
            "metric",
            "unit",
            "manufacturing_run_id",
        ],
    )
    has_data = any(tables.values())
    limitations = []
    if version == "1":
        limitations.append(
            "v1 lacks explicit manufacturing run/block/sequence, condition scope, retry parent and declared raw SHA-256 linkage; no automatic upgrade performed"
        )
    if not has_data:
        limitations.append(
            "Header-only template: no row declares schema version or origin, no execution data"
        )
    return {
        "structural_valid": not errors,
        "schema_version": version,
        "data_origin": next(iter(origins)) if len(origins) == 1 else None,
        "has_data": has_data,
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "errors": errors,
        "provenance": provenance,
        "traceability_limitations": limitations,
        "scientific_usable": False,
        "m1_ready": False,
        "scientific_gates": [
            "material_specification",
            "measurement_method",
            "actual_equipment",
            "actual_conditions",
            "quality_review",
            "task_state_history_not_established_by_snapshot",
            "execution_resources_and_permissions",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    report = validate_bundle(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["structural_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
