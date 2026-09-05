"""Closed pure numerical authored interface. No project code executes on validation."""
from __future__ import annotations

import ast
import copy
import csv
import io
import json
import math
import operator
import sys
import hashlib
from pathlib import Path

OUTPUTS = (
    "experiment/package_manifest.json",
    "experiment/package_contract.json",
    "experiment/self_test_fixture.json",
    "experiment/code/README.md",
    "experiment/code/main.py",
    "experiment/code/algorithm.py",
    "experiment/code/config.json",
    "experiment/code/self_test_config.json",
)

WRAPPER = 'from researchclaw.core.agent_experiment_runtime import main\n\nif __name__ == "__main__":\n    main()\n'
METRIC_IMPLEMENTATION = "researchclaw.core.agent_experiment:mean_absolute_error"
ROLES = ["train", "validation", "calibration", "test"]
BUILTINS = {"sum": sum, "len": len, "min": min, "max": max, "abs": abs}
ALLOWED = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Subscript,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.ListComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Call,
    ast.For,
    ast.If,
    ast.IfExp,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
)


def validate_algorithm(source: str) -> ast.Module:
    if len(source.encode()) > 64 * 1024:
        raise ValueError("algorithm source exceeds bound")
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ValueError("algorithm syntax invalid") from error
    if [node.name for node in tree.body if isinstance(node, ast.FunctionDef)] != [
        "fit",
        "predict",
    ] or len(tree.body) != 2:
        raise ValueError("algorithm must define only fit and predict")
    for fn, args in zip(
        tree.body, (["train_rows", "config"], ["model", "feature_rows", "config"])
    ):
        if (
            fn.decorator_list
            or fn.returns
            or fn.args.defaults
            or fn.args.kw_defaults
            or fn.args.kwonlyargs
            or fn.args.posonlyargs
            or fn.args.vararg
            or fn.args.kwarg
            or [a.arg for a in fn.args.args] != args
            or any(a.annotation for a in fn.args.args)
        ):
            raise ValueError("algorithm signature invalid")
        for node in ast.walk(fn):
            if not isinstance(node, ALLOWED):
                raise ValueError("algorithm prohibited syntax")
            if isinstance(node, ast.FunctionDef) and node is not fn:
                raise ValueError("algorithm nested functions prohibited")
            if isinstance(node, ast.Name) and (
                node.id.startswith("_")
                or (isinstance(node.ctx, ast.Store) and node.id in BUILTINS)
            ):
                raise ValueError("algorithm prohibited name")
            if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name)
                or node.func.id not in BUILTINS
                or node.keywords
            ):
                raise ValueError("algorithm prohibited call")
            if (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Pow)
                and (
                    not isinstance(node.right, ast.Constant)
                    or not isinstance(node.right.value, int)
                    or not 0 <= node.right.value <= 8
                )
            ):
                raise ValueError(
                    "algorithm power must have a literal exponent from 0 to 8"
                )
            if isinstance(node, (ast.For, ast.comprehension)) and (
                not isinstance(node.iter, (ast.Name, ast.ListComp))
                or getattr(node, "is_async", 0)
            ):
                raise ValueError(
                    "algorithm iteration must use supplied data or local collections"
                )
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if any(not isinstance(t, ast.Name) for t in targets):
                    raise ValueError("algorithm assignments must be local names")
    return tree


def finite(value):
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    except OverflowError:
        return False


def mean_absolute_error(targets, predictions):
    if (
        not isinstance(targets, list)
        or not isinstance(predictions, list)
        or not targets
        or len(targets) != len(predictions)
        or not all(finite(x) for x in targets + predictions)
    ):
        raise ValueError("metric requires equal nonempty finite vectors")
    value = sum(abs(a - b) for a, b in zip(targets, predictions)) / len(targets)
    if not finite(value):
        raise ValueError("metric is not finite")
    return value


def decode_rows(payload: bytes, columns: dict):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    expected = [columns[k] for k in ("identity", "group", "split", "target")] + columns[
        "features"
    ]
    if (
        reader.fieldnames is None
        or len(reader.fieldnames) != len(expected)
        or set(reader.fieldnames) != set(expected)
    ):
        raise ValueError("CSV columns do not match declared columns")
    partitions = {role: [] for role in ROLES}
    identities, groups = set(), {}
    for raw in reader:
        if (
            sum(len(rows) for rows in partitions.values()) >= 100000
            or None in raw
            or any(v is None or not v.strip() for v in raw.values())
        ):
            raise ValueError("CSV row is invalid or exceeds bound")
        identity, group, role = (
            raw[columns[k]] for k in ("identity", "group", "split")
        )
        if identity in identities or role not in partitions:
            raise ValueError("CSV duplicate identity or invalid role")
        if group in groups and groups[group] != role:
            raise ValueError("CSV group leakage")
        identities.add(identity)
        groups[group] = role
        row = {
            name: float(raw[name]) for name in [*columns["features"], columns["target"]]
        }
        if not all(finite(v) for v in row.values()):
            raise ValueError("CSV numeric values must be finite")
        partitions[role].append(row)
    if any(not rows for rows in partitions.values()):
        raise ValueError("CSV requires all four nonempty partitions")
    summary = {
        "isolation_key": columns["identity"],
        "roles": {
            r: {
                "cell_count": len(partitions[r]),
                "group_count": sum(v == r for v in groups.values()),
            }
            for r in ROLES
        },
        "cell_overlap_count": 0,
        "group_overlap_count": 0,
        "leakage_count": 0,
    }
    return partitions, summary


def _numeric_operation(name, left, right):
    if not finite(left) or not finite(right):
        raise ValueError("algorithm arithmetic requires finite numbers")
    operation = {
        "Add": operator.add,
        "Sub": operator.sub,
        "Mult": operator.mul,
        "Div": operator.truediv,
        "Pow": operator.pow,
        "Mod": operator.mod,
    }[name]
    result = operation(float(left), float(right))
    if not finite(result):
        raise ValueError("algorithm arithmetic must remain finite")
    return result


class _NumericalArithmetic(ast.NodeTransformer):
    def visit_BinOp(self, node):
        self.generic_visit(node)
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id="_numeric", ctx=ast.Load()),
                args=[ast.Constant(type(node.op).__name__), node.left, node.right],
                keywords=[],
            ),
            node,
        )

    def visit_AugAssign(self, node):
        value = self.visit_BinOp(
            ast.copy_location(
                ast.BinOp(
                    left=ast.Name(id=node.target.id, ctx=ast.Load()),
                    op=node.op,
                    right=node.value,
                ),
                node,
            )
        )
        return ast.copy_location(ast.Assign(targets=[node.target], value=value), node)


def _bounded_model(model):
    # Count occurrences, not unique objects: shared containers expand in JSON.
    remaining = 10000
    string_bytes = 0

    def visit(value, depth):
        nonlocal remaining, string_bytes
        remaining -= 1
        if remaining < 0 or depth > 64:
            raise ValueError("model serialization budget exceeded")
        if isinstance(value, str):
            string_bytes += len(value.encode("utf-8"))
            if string_bytes > 1024 * 1024:
                raise ValueError("model serialization budget exceeded")
        elif value is None or isinstance(value, bool):
            return
        elif isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError("model must contain finite numbers")
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("model keys must be strings")
                visit(key, depth + 1)
                visit(item, depth + 1)
        else:
            raise ValueError("model must be JSON-compatible")

    visit(model, 0)
    encoded = json.dumps(model, allow_nan=False)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise ValueError("model serialization budget exceeded")
    return json.loads(encoded)


def evaluate(source, partitions, columns, parameters):
    tree = validate_algorithm(source)
    tree = ast.fix_missing_locations(_NumericalArithmetic().visit(tree))
    namespace = {"__builtins__": BUILTINS, "_numeric": _numeric_operation}
    code = compile(tree, "<authored-algorithm>", "exec")
    remaining = 1000000

    def budget(frame, event, arg):
        nonlocal remaining
        if frame.f_code.co_filename == "<authored-algorithm>":
            frame.f_trace_opcodes = True
            remaining -= 1
            if remaining <= 0:
                raise ValueError("algorithm instruction budget exceeded")
        return budget

    prior = sys.gettrace()
    try:
        sys.settrace(budget)
        exec(code, namespace)
        model = namespace["fit"](
            copy.deepcopy(partitions["train"]), copy.deepcopy(parameters)
        )
        model = _bounded_model(model)
        rows = [
            {name: row[name] for name in columns["features"]}
            for row in partitions["test"]
        ]
        predictions = namespace["predict"](
            copy.deepcopy(model), rows, copy.deepcopy(parameters)
        )
    finally:
        sys.settrace(prior)
    value = mean_absolute_error(
        [row[columns["target"]] for row in partitions["test"]], predictions
    )
    return model, predictions, value


def runtime_identity():
    return {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in (
            "agent_experiment.py",
            "agent_experiment_runtime.py",
            "execution_environment.py",
        )
    }


def validate_package(
    root, *, candidate=False, project_id=None, design_sha256=None, design=None
):
    """Validate both layouts without loading authored code; return held package bytes."""
    from .experiment_package_contract import (
        _read_json_object,
        _read_candidate_package_bytes,
        _require_closed,
        PACKAGE_KEYS,
    )

    layout = (
        {
            "manifest": "package_metadata/package_manifest.json",
            "contract": "package_metadata/package_contract.json",
            "entry": "code/model.py",
            "algorithm": "code/algorithm.py",
            "config": "config/config.json",
            "self_config": "tests/self_test_config.json",
            "fixture": "tests/self_test_fixture.json",
            "result": "results.json",
            "report": "package_metadata/self_test_report.json",
        }
        if candidate
        else {
            "manifest": "experiment/package_manifest.json",
            "contract": "experiment/package_contract.json",
            "entry": "experiment/code/main.py",
            "algorithm": "experiment/code/algorithm.py",
            "config": "experiment/code/config.json",
            "self_config": "experiment/code/self_test_config.json",
            "fixture": "experiment/self_test_fixture.json",
            "result": "experiment/results.json",
            "report": "experiment/self_test_report.json",
        }
    )
    manifest, manifest_bytes = _read_json_object(
        root, layout["manifest"], candidate_rooted=True
    )
    _require_closed(
        manifest,
        {
            "schema_version",
            "project_id",
            "design_sha256",
            "validation_type",
            "entry_point",
            "config_path",
            "files",
        },
        "v2 manifest",
    )
    if (
        not isinstance(manifest["schema_version"], int)
        or manifest["schema_version"] != 2
        or manifest["validation_type"] != "computational"
    ):
        raise ValueError("v2 manifest discriminator invalid")
    expected = set(layout.values()) - {
        layout[k] for k in ("manifest", "result", "report")
    }
    if not candidate:
        expected.add("experiment/code/README.md")
    held = {layout["manifest"]: manifest_bytes}
    if not isinstance(manifest["files"], list):
        raise ValueError("v2 files must be list")
    for entry in manifest["files"]:
        _require_closed(entry, {"path", "role", "sha256"}, "v2 file")
        path = entry["path"]
        if path not in expected or path in held or not isinstance(entry["role"], str):
            raise ValueError("v2 file set invalid")
        payload = _read_candidate_package_bytes(root, path, maximum_bytes=1024 * 1024)
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("v2 package file hash changed")
        held[path] = payload
    if set(held) != expected | {layout["manifest"]}:
        raise ValueError("v2 file set incomplete")
    code_root = root / ("code" if candidate else "experiment/code")
    for path in code_root.rglob("*"):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.relative_to(root).as_posix() not in held
        ):
            raise ValueError("v2 code tree contains undeclared files")
    contract, _ = _read_json_object(root, layout["contract"], candidate_rooted=True)
    _require_closed(
        contract, PACKAGE_KEYS | {"algorithm_path", "runtime_sha256"}, "v2 contract"
    )
    if (
        not isinstance(contract["schema_version"], int)
        or contract["schema_version"] != 2
        or contract["runtime_sha256"] != runtime_identity()
    ):
        raise ValueError("v2 runtime identity changed")
    for key, local in (
        ("entry_point", "entry"),
        ("algorithm_path", "algorithm"),
        ("config_path", "config"),
        ("result_path", "result"),
    ):
        if contract[key] != layout[local]:
            raise ValueError("v2 contract path invalid")
    if (
        manifest["entry_point"] != layout["entry"]
        or manifest["config_path"] != layout["config"]
        or held[layout["entry"]].decode() != WRAPPER
    ):
        raise ValueError("v2 wrapper must be canonical")
    validate_algorithm(held[layout["algorithm"]].decode())
    if (
        contract["dependencies"] != []
        or contract["prohibitions"]
        != {
            "network_access": False,
            "external_llm_calls": False,
            "nested_agent_processes": False,
        }
        or any(v is not False for v in contract["prohibitions"].values())
    ):
        raise ValueError("v2 dependencies or prohibitions invalid")
    self_test = _require_closed(
        contract["self_test"],
        {"argv_suffix", "fixture_path", "expected_metrics"},
        "v2 self test",
    )
    if (
        self_test["argv_suffix"] != ["--config", layout["self_config"], "--self-test"]
        or self_test["fixture_path"] != layout["fixture"]
        or contract["execution"] != {"argv_suffix": ["--config", layout["config"]]}
    ):
        raise ValueError("v2 execution arguments invalid")
    cfg, _ = _read_json_object(root, layout["config"], candidate_rooted=True)
    _require_closed(
        cfg,
        {
            "schema_version",
            "project_id",
            "design_sha256",
            "input_contract",
            "split_strategy",
            "columns",
            "parameters",
            "metrics",
        },
        "v2 config",
    )
    if (
        not isinstance(cfg["schema_version"], int)
        or cfg["schema_version"] != 2
        or cfg["project_id"] != manifest["project_id"]
        or cfg["design_sha256"] != manifest["design_sha256"]
        or (project_id is not None and cfg["project_id"] != project_id)
        or (design_sha256 is not None and cfg["design_sha256"] != design_sha256)
    ):
        raise ValueError("v2 design binding invalid")
    columns = _require_closed(
        cfg["columns"],
        {"identity", "group", "split", "target", "features"},
        "v2 columns",
    )
    if not isinstance(columns["features"], list) or not columns["features"]:
        raise ValueError("v2 features invalid")
    names = [columns[k] for k in ("identity", "group", "split", "target")] + columns[
        "features"
    ]
    if any(not isinstance(n, str) or not n or n.startswith("_") for n in names) or len(
        set(names)
    ) != len(names):
        raise ValueError("v2 column names must be distinct")
    if cfg["split_strategy"] != {
        "isolation_key": columns["identity"],
        "overlap_policy": "disjoint",
        "groups": ROLES,
    }:
        raise ValueError("v2 split strategy invalid")
    inputs = _require_closed(cfg["input_contract"], {"required_paths"}, "v2 inputs")[
        "required_paths"
    ]
    from .paths import resolve_project_artifact

    if (
        not isinstance(inputs, list)
        or len(inputs) != 1
        or not isinstance(inputs[0], str)
        or not inputs[0].endswith(".csv")
    ):
        raise ValueError("v2 requires one CSV input")
    resolve_project_artifact(root, inputs[0])
    if not isinstance(cfg["parameters"], dict):
        raise ValueError("v2 parameters must be object")
    metrics = cfg["metrics"]
    if not isinstance(metrics, list) or len(metrics) != 1:
        raise ValueError("v2 supports only mae")
    metric = _require_closed(metrics[0], {"name", "unit"}, "v2 metric")
    if (
        metric["name"] != "mae"
        or not isinstance(metric["unit"], str)
        or not metric["unit"]
        or contract["metrics"] != [{**metric, "implementation": METRIC_IMPLEMENTATION}]
    ):
        raise ValueError("v2 supports only mae with matching unit")
    if design is not None:
        if [
            {"name": m["name"], "unit": m["unit"]} for m in design["metrics"]
        ] != metrics or design["method"]["split_strategy"].get(
            "isolation_key"
        ) != columns["identity"]:
            raise ValueError("v2 metric or isolation differs from approved design")
    expected_metrics = self_test["expected_metrics"]
    if not isinstance(expected_metrics, list) or len(expected_metrics) != 1:
        raise ValueError("v2 expected metric invalid")
    answer = _require_closed(
        expected_metrics[0], {"name", "expected", "tolerance"}, "v2 expected metric"
    )
    if (
        answer["name"] != "mae"
        or not finite(answer["expected"])
        or not finite(answer["tolerance"])
        or answer["tolerance"] < 0
    ):
        raise ValueError("v2 expected metric invalid")
    self_cfg, _ = _read_json_object(root, layout["self_config"], candidate_rooted=True)
    if self_cfg != {"schema_version": 2, "fixture_path": layout["fixture"]}:
        raise ValueError("v2 self-test config invalid")
    fixture, _ = _read_json_object(root, layout["fixture"], candidate_rooted=True)
    _require_closed(fixture, {"targets", "predictions"}, "v2 fixture")
    mean_absolute_error(fixture["targets"], fixture["predictions"])
    for path, payload in held.items():
        if (
            _read_candidate_package_bytes(root, path, maximum_bytes=1024 * 1024)
            != payload
        ):
            raise ValueError("v2 package changed during validation")
    return layout, manifest, contract, cfg, fixture, held
