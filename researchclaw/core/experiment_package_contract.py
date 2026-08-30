"""Closed Stage-10 experiment-package and development self-test contracts."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .computational_package import validate_python_capability_safety
from .models import ArtifactRef
from .paths import resolve_project_artifact
from .project import ResearchProject


EXPERIMENT_PACKAGE_CONTRACT_PATH = "experiment/package_contract.json"
SELF_TEST_REPORT_PATH = "experiment/self_test_report.json"
_PACKAGE_MANIFEST_PATH = "experiment/package_manifest.json"
_MAX_JSON_BYTES = 1024 * 1024
_MAX_FIXTURE_JSON_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PACKAGE_KEYS = {
    "schema_version", "entry_point", "config_path", "result_path",
    "metrics", "self_test", "execution", "dependencies", "prohibitions",
}
METRIC_KEYS = {"name", "unit", "implementation"}
SELF_TEST_KEYS = {"argv_suffix", "fixture_path", "expected_metrics"}
_EXECUTION_KEYS = {"argv_suffix"}
_EXPECTED_METRIC_KEYS = {"name", "expected", "tolerance"}
_REPORT_KEYS = {
    "schema_version", "package_contract", "fixture", "environment_fingerprint",
    "package_manifest", "entry_point", "package_files", "metrics", "passed",
    "development_only",
}
_IDENTITY_KEYS = {"path", "sha256"}
_REPORT_METRIC_KEYS = {"name", "actual", "expected", "tolerance"}


@dataclass(frozen=True)
class ValidatedExperimentPackage:
    contract_sha256: str
    metric_entrypoints: Mapping[str, str]
    self_test_argv: tuple[str, ...]
    execution_argv: tuple[str, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if not isinstance(key, str) or key in value:
            raise ValueError("JSON keys must be unique strings")
        value[key] = item
    return value


def _read_json_object(
    root: Path,
    relative_path: str,
    *,
    maximum_bytes: int = _MAX_JSON_BYTES,
    label: str = "JSON artifact",
) -> tuple[dict[str, Any], bytes]:
    path = resolve_project_artifact(root, relative_path)
    if not path.is_file():
        raise ValueError(f"required artifact is missing: {relative_path}")
    if path.stat().st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the bound: {relative_path}")
    payload = path.read_bytes()
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda raw: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {raw}")
            ),
        )
    except ValueError as error:
        if str(error).startswith(("non-finite JSON number:", "JSON keys must be unique")):
            raise
        raise ValueError(f"invalid JSON object: {relative_path}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON object: {relative_path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {relative_path}")
    return value, payload


def _require_closed(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if unknown:
        raise ValueError(f"{label} has undeclared fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{label} requires fields: {', '.join(missing)}")
    return value


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _schema_version_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


def _required_path(root: Path, value: object, label: str) -> tuple[str, Path]:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a project-relative path")
    path = resolve_project_artifact(root, value)
    if not path.is_file():
        raise ValueError(f"{label} must identify a regular file")
    return value, path


def _argv_suffix(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{label} argv_suffix must be a non-empty string list")
    return tuple(value)


def _argv_config_path(argv: tuple[str, ...], label: str) -> str:
    positions = [index for index, item in enumerate(argv) if item == "--config"]
    if any(item.startswith("--config=") for item in argv) or len(positions) != 1:
        raise ValueError(f"{label} argv_suffix must contain exactly one --config")
    position = positions[0]
    if position != 0 or position + 1 >= len(argv) or argv[1].startswith("-"):
        raise ValueError(f"{label} argv_suffix must begin with --config and its input")
    return argv[position + 1]


def _package_main_source(
    root: Path, entry_point: object
) -> tuple[str, ast.Module, str, str]:
    entry_path, path = _required_path(root, entry_point, "entry_point")
    if not entry_path.startswith("experiment/code/") or not entry_path.endswith(".py"):
        raise ValueError("entry_point must be a package-manifest Python file")
    manifest, manifest_bytes = _read_json_object(root, _PACKAGE_MANIFEST_PATH)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("package manifest files must be a list")
    declared_paths: set[str] = set()
    for file_entry in files:
        if not isinstance(file_entry, dict):
            raise ValueError("package manifest files must contain objects")
        relative_path = file_entry.get("path")
        declared_sha256 = file_entry.get("sha256")
        if (
            not isinstance(relative_path, str)
            or relative_path in declared_paths
            or not isinstance(declared_sha256, str)
            or _SHA256.fullmatch(declared_sha256) is None
        ):
            raise ValueError("package manifest file identity is invalid")
        declared_paths.add(relative_path)
        _path, declared_file = _required_path(root, relative_path, "package manifest file")
        if hashlib.sha256(declared_file.read_bytes()).hexdigest() != declared_sha256:
            raise ValueError("package manifest identity does not match its declared file")
    entries = [item for item in files if isinstance(item, dict) and item.get("path") == entry_path]
    if len(entries) != 1 or set(entries[0]) - {"path", "role", "sha256"}:
        raise ValueError("entry_point must be declared once by the package manifest")
    expected_hash = entries[0].get("sha256")
    source_bytes = path.read_bytes()
    if not isinstance(expected_hash, str) or hashlib.sha256(source_bytes).hexdigest() != expected_hash:
        raise ValueError("package manifest identity does not match entry_point")
    try:
        source = source_bytes.decode("utf-8")
        tree = ast.parse(source, filename=entry_path)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise ValueError("entry_point must contain valid Python") from error
    return (
        source,
        tree,
        hashlib.sha256(manifest_bytes).hexdigest(),
        hashlib.sha256(source_bytes).hexdigest(),
    )


def _module_name(entry_path: str) -> str:
    return entry_path.removesuffix(".py").replace("/", ".")


def _top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _function_aliases(
    tree: ast.Module, functions: Mapping[str, ast.FunctionDef]
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Name):
            continue
        target_names = (
            [target.id for target in node.targets if isinstance(target, ast.Name)]
            if isinstance(node, ast.Assign)
            else [node.target.id] if isinstance(node.target, ast.Name) else []
        )
        value_name = node.value.id
        resolved = aliases.get(value_name, value_name)
        if resolved in functions or resolved == "dict":
            aliases.update({target: resolved for target in target_names})
    return aliases


def _local_call_name(node: ast.Call, aliases: Mapping[str, str]) -> str | None:
    if not isinstance(node.func, ast.Name):
        return None
    return aliases.get(node.func.id, node.func.id)


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> tuple[ast.AST, ...]:
    return tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)


def _local_alias_target(function: ast.FunctionDef, call: ast.Call) -> tuple[str | None, bool]:
    """Resolve a local callable alias using only source-order-reachable definitions."""
    if not isinstance(call.func, ast.Name):
        return None, False

    assignments = sorted(
        [
            node for node in ast.walk(function)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ],
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )

    def resolve(name: str, before: tuple[int, int], seen: set[str]) -> tuple[str, bool]:
        definitions = [
            node for node in assignments
            if (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)) < before
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in _assignment_targets(node)
            )
        ]
        if not definitions:
            return name, bool(seen)
        if len(definitions) != 1 or not isinstance(definitions[0].value, ast.Name):
            raise ValueError("callable alias is ambiguous or reassigned")
        if name in seen:
            raise ValueError("callable alias is cyclic or ambiguous")
        definition = definitions[0]
        return resolve(
            definition.value.id,
            (getattr(definition, "lineno", 0), getattr(definition, "col_offset", 0)),
            {*seen, name},
        )

    return resolve(call.func.id, (getattr(call, "lineno", 0), getattr(call, "col_offset", 0)), set())


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for imported in node.names:
                aliases[imported.asname or imported.name.split(".")[0]] = imported.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for imported in node.names:
                aliases[imported.asname or imported.name] = f"{node.module}.{imported.name}"
    return aliases


def _dotted_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent is not None else None
    if isinstance(node, ast.Call):
        parent = _dotted_name(node.func, aliases)
        return f"{parent}()" if parent is not None else None
    return None


def _reachable_metric_nodes(
    function: ast.FunctionDef,
    functions: Mapping[str, ast.FunctionDef],
    function_aliases: Mapping[str, str],
) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    queued = [function]
    visited: set[str] = set()
    while queued:
        current = queued.pop()
        if current.name in visited:
            continue
        visited.add(current.name)
        nodes.extend(ast.walk(current))
        for node in ast.walk(current):
            if isinstance(node, ast.Call):
                target_name, local_alias = _local_alias_target(current, node)
                if target_name is None or not local_alias:
                    target_name = _local_call_name(node, function_aliases)
                elif local_alias and target_name not in functions and target_name != "dict":
                    raise ValueError("callable alias is unresolved or ambiguous")
                target = functions.get(target_name or "")
                if target is not None:
                    queued.append(target)
    return nodes


def _has_size_proxy(nodes: list[ast.AST], aliases: Mapping[str, str]) -> bool:
    for node in nodes:
        if isinstance(node, ast.Attribute) and node.attr == "st_size":
            return True
        if isinstance(node, ast.Subscript) and any(
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Attribute)
            and candidate.func.attr == "stat"
            for candidate in ast.walk(node.value)
        ):
            return True
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func, aliases)
        if name in {"os.path.getsize", "Path().stat", "pathlib.Path().stat"}:
            return True
        if name == "len" and node.args and isinstance(node.args[0], ast.Name):
            if re.search(r"(?:raw|input|file|payload).*bytes", node.args[0].id, re.I):
                return True
    return False


def _has_evidence_eligible_fallback(tree: ast.Module) -> bool:
    functions = _top_level_functions(tree)
    function_aliases = _function_aliases(tree, functions)
    for function in functions.values():
        if re.search(r"(?:fallback|placeholder)", function.name, re.I) is None:
            continue
        for node in _reachable_metric_nodes(function, functions, function_aliases):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "evidence_eligible"
                        and isinstance(value, ast.Constant)
                        and value.value is True
                    ):
                        return True
            if not isinstance(node, ast.Call):
                continue
            local_target, local_alias = _local_alias_target(function, node)
            target_name = (
                local_target if local_alias else _local_call_name(node, function_aliases)
            )
            if (
                target_name == "dict"
                and any(
                    keyword.arg == "evidence_eligible"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                )
            ):
                return True
    return False


def _is_positive_self_test_condition(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "args"
        and node.attr == "self_test"
    )


def _mentions_self_test(node: ast.AST) -> bool:
    return any(
        isinstance(candidate, ast.Attribute)
        and isinstance(candidate.value, ast.Name)
        and candidate.value.id == "args"
        and candidate.attr == "self_test"
        for candidate in ast.walk(node)
    )


def _metric_source(
    expression: ast.AST,
    scalars: Mapping[str, str | None],
    mappings: Mapping[str, str | None],
) -> str | None:
    if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
        return expression.func.id
    if isinstance(expression, ast.Name):
        return scalars.get(expression.id)
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Name)
        and isinstance(expression.slice, ast.Constant)
        and isinstance(expression.slice.value, str)
    ):
        return mappings.get(f"{expression.value.id}:{expression.slice.value}")
    return None


def _dict_fields(node: ast.Dict) -> dict[str, ast.AST]:
    return {
        key.value: value
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _is_self_test_report_write(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "write_text":
        return False
    target = call.func.value
    return (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id == "Path"
        and len(target.args) == 1
        and isinstance(target.args[0], ast.Constant)
        and target.args[0].value == SELF_TEST_REPORT_PATH
    )


def _self_test_report_payload_name(call: ast.Call) -> str | None:
    if not _is_self_test_report_write(call):
        return None
    if not call.args:
        return None
    payload = call.args[0]
    serializer = payload.left if isinstance(payload, ast.BinOp) and isinstance(payload.op, ast.Add) else payload
    if not isinstance(serializer, ast.Call):
        return None
    if not (
        isinstance(serializer.func, ast.Attribute)
        and isinstance(serializer.func.value, ast.Name)
        and serializer.func.value.id == "json"
        and serializer.func.attr == "dumps"
        and serializer.args
        and isinstance(serializer.args[0], ast.Name)
    ):
        return None
    return serializer.args[0].id


def _mapping_is_mutated_before_write(nodes: list[ast.AST], write: ast.Call) -> bool:
    write_position = (getattr(write, "lineno", 0), getattr(write, "col_offset", 0))
    for node in nodes:
        position = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
        if position >= write_position:
            continue
        if isinstance(node, ast.AugAssign) and (
            isinstance(node.target, (ast.Name, ast.Subscript))
            or isinstance(node.op, ast.BitOr)
        ):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
            isinstance(target, ast.Subscript) for target in _assignment_targets(node)
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"update", "setdefault", "clear", "pop", "popitem", "__ior__"}
        ):
            return True
    return False


def _validate_self_test_adapter(
    tree: ast.Module, metric_entrypoints: Mapping[str, str]
) -> None:
    """Prove that the written self-test report carries declared metric values."""
    main = _top_level_functions(tree).get("main")
    if main is None:
        raise ValueError("self-test adapter requires a top-level main function")
    functions = _top_level_functions(tree)
    function_aliases = _function_aliases(tree, functions)
    branches = [
        node for node in ast.walk(main)
        if isinstance(node, ast.If) and _is_positive_self_test_condition(node.test)
    ]
    mentioned_branches = [
        node for node in ast.walk(main)
        if isinstance(node, ast.If) and _mentions_self_test(node.test)
    ]
    if len(branches) != 1 or len(mentioned_branches) != 1:
        raise ValueError("self-test adapter must have one unambiguous --self-test branch")
    nodes = [item for statement in branches[0].body for item in ast.walk(statement)]
    if any(
        isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try))
        for node in nodes
    ):
        raise ValueError("self-test adapter must not use ambiguous provenance branches")
    all_nodes = _reachable_metric_nodes(main, functions, function_aliases)
    writes = [
        (node, _self_test_report_payload_name(node))
        for node in all_nodes
        if isinstance(node, ast.Call) and _is_self_test_report_write(node)
    ]
    if len(writes) != 1 or writes[0][0] not in nodes or writes[0][1] is None:
        raise ValueError("self-test adapter must write exactly one self-test report")
    write, report_name = writes[0]
    assert report_name is not None
    if _mapping_is_mutated_before_write(nodes, write):
        raise ValueError("self-test adapter rejects mutable report provenance")
    write_line = getattr(write, "lineno", 0)
    assignments = sorted(
        [
            node for node in nodes
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and getattr(node, "lineno", 0) < write_line
        ],
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )
    report_definitions = [
        node for node in assignments
        if any(
            isinstance(target, ast.Name) and target.id == report_name
            for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        )
    ]
    if len(report_definitions) != 1 or not isinstance(report_definitions[0].value, ast.Dict):
        raise ValueError("self-test adapter report object is ambiguous")

    scalars: dict[str, str | None] = {}
    mappings: dict[str, str | None] = {}
    for node in assignments:
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        source = _metric_source(node.value, scalars, mappings)
        for target in targets:
            if isinstance(target, ast.Name):
                scalars[target.id] = source
                if isinstance(node.value, ast.Dict):
                    for key, value in _dict_fields(node.value).items():
                        mappings[f"{target.id}:{key}"] = _metric_source(
                            value, scalars, mappings
                        )
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                mappings[f"{target.value.id}:{target.slice.value}"] = source

    report_fields = _dict_fields(report_definitions[0].value)
    records = report_fields.get("metrics")
    if not isinstance(records, ast.List):
        raise ValueError("self-test adapter report must contain literal metric records")
    selected_records = [node for node in records.elts if isinstance(node, ast.Dict)]
    if len(selected_records) != len(metric_entrypoints):
        raise ValueError("self-test adapter report metric set is ambiguous")
    for metric_name, implementation in metric_entrypoints.items():
        function_name = implementation.partition(":")[2]
        matching = [
            record for record in selected_records
            if _dict_fields(record).get("name")
            and isinstance(_dict_fields(record)["name"], ast.Constant)
            and _dict_fields(record)["name"].value == metric_name
        ]
        if len(matching) != 1 or _metric_source(
            _dict_fields(matching[0]).get("actual", ast.Constant(None)), scalars, mappings
        ) != function_name:
            raise ValueError(
                "self-test adapter must construct each written actual metric from its declared implementation"
            )

    for node in nodes:
        if not isinstance(node, ast.Dict) or node in selected_records:
            continue
        fields = _dict_fields(node)
        if (
            isinstance(fields.get("name"), ast.Constant)
            and fields["name"].value in metric_entrypoints
            and "actual" in fields
        ):
            raise ValueError("self-test adapter rejects unused metric records")


def _validate_metrics(
    metrics_value: object,
    expected_value: object,
    entry_point: str,
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, tuple[float, float]]]:
    if not isinstance(metrics_value, list) or not metrics_value:
        raise ValueError("metrics must be a non-empty list")
    if not isinstance(expected_value, list) or not expected_value:
        raise ValueError("expected_metrics must be a non-empty list")
    functions = _top_level_functions(tree)
    function_aliases = _function_aliases(tree, functions)
    aliases = _import_aliases(tree)
    module = _module_name(entry_point)
    metrics: dict[str, str] = {}
    for metric in metrics_value:
        item = _require_closed(metric, METRIC_KEYS, "metric")
        name, unit, implementation = item["name"], item["unit"], item["implementation"]
        if not isinstance(name, str) or not name or not isinstance(unit, str) or not unit:
            raise ValueError("metric name and unit must be non-empty strings")
        if name in metrics:
            raise ValueError("metric names must be unique")
        if not isinstance(implementation, str) or not implementation.startswith(f"{module}:"):
            raise ValueError("metric implementation must bind to the package entry_point")
        function_name = implementation.partition(":")[2]
        function = functions.get(function_name)
        if function is None:
            raise ValueError("metric implementation must resolve to a top-level function")
        if _has_size_proxy(
            _reachable_metric_nodes(function, functions, function_aliases), aliases
        ):
            raise ValueError("metric implementation must not use an input or file size proxy")
        metrics[name] = implementation
    expected: dict[str, tuple[float, float]] = {}
    for metric in expected_value:
        item = _require_closed(metric, _EXPECTED_METRIC_KEYS, "expected metric")
        name, value, tolerance = item["name"], item["expected"], item["tolerance"]
        if not isinstance(name, str) or not name:
            raise ValueError("expected metric name must be text")
        if name in expected:
            raise ValueError("expected metric names must be unique")
        if not _finite_number(value) or not _finite_number(tolerance) or tolerance < 0:
            raise ValueError("expected metric value and tolerance must be finite")
        expected[name] = (float(value), float(tolerance))
    if set(metrics) != set(expected):
        raise ValueError("expected metric set must match metrics")
    if _has_evidence_eligible_fallback(tree):
        raise ValueError("placeholder fallback must not be evidence eligible")
    return metrics, expected


def validate_experiment_package_contract(project: ResearchProject) -> ValidatedExperimentPackage:
    """Validate the non-executing closed package contract for a project."""
    contract, contract_bytes = _read_json_object(project.root, EXPERIMENT_PACKAGE_CONTRACT_PATH)
    _require_closed(contract, PACKAGE_KEYS, "package contract")
    if not _schema_version_one(contract["schema_version"]):
        raise ValueError("package contract schema_version must equal 1")
    entry_point = contract["entry_point"]
    if not isinstance(entry_point, str):
        raise ValueError("entry_point must be text")
    source, tree, _manifest_sha256, _entry_point_sha256 = _package_main_source(
        project.root, entry_point
    )
    config_path, _config = _required_path(project.root, contract["config_path"], "config_path")
    result_path = contract["result_path"]
    if result_path != "experiment/results.json":
        raise ValueError("result_path must be experiment/results.json")
    self_test = _require_closed(contract["self_test"], SELF_TEST_KEYS, "self_test")
    execution = _require_closed(contract["execution"], _EXECUTION_KEYS, "execution")
    self_test_argv = _argv_suffix(self_test["argv_suffix"], "self_test")
    execution_argv = _argv_suffix(execution["argv_suffix"], "execution")
    if self_test_argv == execution_argv:
        raise ValueError("self-test and execution argv_suffix values must be distinct")
    if self_test_argv[-1] != "--self-test" or "--self-test" in execution_argv:
        raise ValueError("self_test argv_suffix must end with --self-test")
    self_test_config = _argv_config_path(self_test_argv, "self_test")
    execution_config = _argv_config_path(execution_argv, "execution")
    _required_path(project.root, self_test_config, "self_test input")
    if execution_config != config_path or self_test_config == execution_config:
        raise ValueError("self-test and research inputs must be distinct")
    fixture_path, fixture = _required_path(project.root, self_test["fixture_path"], "self_test fixture")
    if fixture_path in {config_path, self_test_config} or fixture.stat().st_size == 0:
        raise ValueError("self_test fixture must be a non-empty distinct input")
    fixture_value, _fixture_bytes = _read_json_object(
        project.root,
        fixture_path,
        maximum_bytes=_MAX_FIXTURE_JSON_BYTES,
        label="fixture",
    )
    if not fixture_value:
        raise ValueError("self_test fixture must be non-empty")
    if not isinstance(contract["dependencies"], list) or any(
        not isinstance(item, str) or not item for item in contract["dependencies"]
    ):
        raise ValueError("dependencies must be a string list")
    if not isinstance(contract["prohibitions"], dict) or any(
        not isinstance(key, str) or value is not False
        for key, value in contract["prohibitions"].items()
    ):
        raise ValueError("prohibitions must be false-valued declarations")
    metrics, _expected = _validate_metrics(
        contract["metrics"], self_test["expected_metrics"], entry_point, tree
    )
    _validate_self_test_adapter(tree, metrics)
    if validate_python_capability_safety(entry_point, source):
        raise ValueError("entry_point has a prohibited static capability")
    return ValidatedExperimentPackage(
        contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
        metric_entrypoints=MappingProxyType(metrics),
        self_test_argv=self_test_argv,
        execution_argv=execution_argv,
    )


def _validate_identity(value: object, path: str, sha256: str, label: str) -> None:
    identity = _require_closed(value, _IDENTITY_KEYS, label)
    if identity["path"] != path or identity["sha256"] != sha256:
        raise ValueError(f"{label} does not match the current package identity")


def _current_package_file_identities(root: Path) -> list[dict[str, str]]:
    """Return the complete, current closed file identity set declared by the manifest."""
    manifest, _manifest_bytes = _read_json_object(root, _PACKAGE_MANIFEST_PATH)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("package manifest files must be a list")
    identities: list[dict[str, str]] = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) - {"path", "role", "sha256"}:
            raise ValueError("package manifest file identity is invalid")
        path = entry.get("path")
        sha256 = entry.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(sha256, str)
            or _SHA256.fullmatch(sha256) is None
        ):
            raise ValueError("package manifest file identity is invalid")
        identities.append({"path": path, "sha256": sha256})
    return identities


def _validate_package_file_identities(value: object, expected: list[dict[str, str]]) -> None:
    if not isinstance(value, list):
        raise ValueError("package_files must be a list")
    reported: list[dict[str, str]] = []
    for entry in value:
        identity = _require_closed(entry, _IDENTITY_KEYS, "package file identity")
        path, sha256 = identity["path"], identity["sha256"]
        if (
            not isinstance(path, str)
            or not isinstance(sha256, str)
            or _SHA256.fullmatch(sha256) is None
        ):
            raise ValueError("package file identity is invalid")
        reported.append({"path": path, "sha256": sha256})
    if reported != expected:
        raise ValueError("package_files does not match the current package identity")


def validate_registered_self_test(
    project: ResearchProject, package: ValidatedExperimentPackage
) -> ArtifactRef:
    """Validate an externally produced self-test report without recording it."""
    current = validate_experiment_package_contract(project)
    if current != package:
        raise ValueError("package changed since self-test validation")
    contract, _contract_bytes = _read_json_object(project.root, EXPERIMENT_PACKAGE_CONTRACT_PATH)
    self_test = _require_closed(contract["self_test"], SELF_TEST_KEYS, "self_test")
    fixture_path, fixture = _required_path(project.root, self_test["fixture_path"], "self_test fixture")
    report, report_bytes = _read_json_object(project.root, SELF_TEST_REPORT_PATH)
    _require_closed(report, _REPORT_KEYS, "self_test report")
    if not _schema_version_one(report["schema_version"]):
        raise ValueError("self_test report schema_version must equal 1")
    if report["passed"] is not True:
        raise ValueError("self_test report must declare passed true")
    if report["development_only"] is not True:
        raise ValueError("self_test report must declare development_only true")
    _validate_identity(
        report["package_contract"],
        EXPERIMENT_PACKAGE_CONTRACT_PATH,
        package.contract_sha256,
        "package_contract",
    )
    _validate_identity(
        report["package_manifest"],
        _PACKAGE_MANIFEST_PATH,
        hashlib.sha256(
            resolve_project_artifact(project.root, _PACKAGE_MANIFEST_PATH).read_bytes()
        ).hexdigest(),
        "package_manifest",
    )
    _validate_identity(
        report["entry_point"],
        contract["entry_point"],
        hashlib.sha256(
            resolve_project_artifact(project.root, contract["entry_point"]).read_bytes()
        ).hexdigest(),
        "entry_point",
    )
    _validate_package_file_identities(
        report["package_files"], _current_package_file_identities(project.root)
    )
    _validate_identity(
        report["fixture"], fixture_path, hashlib.sha256(fixture.read_bytes()).hexdigest(), "fixture"
    )
    fingerprint = report["environment_fingerprint"]
    if not isinstance(fingerprint, str) or _SHA256.fullmatch(fingerprint) is None:
        raise ValueError("environment fingerprint must be an opaque lowercase SHA-256")
    _metrics, expected = _validate_metrics(
        contract["metrics"], self_test["expected_metrics"], contract["entry_point"], _package_main_source(project.root, contract["entry_point"])[1]
    )
    report_metrics = report["metrics"]
    if not isinstance(report_metrics, list):
        raise ValueError("self_test report metrics must be a list")
    actual_names: set[str] = set()
    for value in report_metrics:
        metric = _require_closed(value, _REPORT_METRIC_KEYS, "self_test report metric")
        name = metric["name"]
        if not isinstance(name, str) or name in actual_names:
            raise ValueError("self_test report metric names must be unique")
        actual_names.add(name)
        if not all(_finite_number(metric[field]) for field in ("actual", "expected", "tolerance")):
            raise ValueError("self_test report metrics must be finite")
        if name not in expected:
            continue
        required_expected, required_tolerance = expected[name]
        if (
            float(metric["expected"]) != required_expected
            or float(metric["tolerance"]) != required_tolerance
            or abs(float(metric["actual"]) - required_expected) > required_tolerance
        ):
            raise ValueError("self_test report metric does not match its known answer")
    if actual_names != set(expected):
        raise ValueError("self_test report metric set does not match the package")
    report_path = resolve_project_artifact(project.root, SELF_TEST_REPORT_PATH)
    return ArtifactRef(
        path=SELF_TEST_REPORT_PATH,
        sha256=hashlib.sha256(report_bytes).hexdigest(),
        size=report_path.stat().st_size,
    )
