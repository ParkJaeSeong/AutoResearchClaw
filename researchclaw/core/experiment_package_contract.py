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
    "metrics", "passed", "development_only",
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


def _read_json_object(root: Path, relative_path: str) -> tuple[dict[str, Any], bytes]:
    path = resolve_project_artifact(root, relative_path)
    if not path.is_file():
        raise ValueError(f"required artifact is missing: {relative_path}")
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError(f"JSON artifact exceeds the bound: {relative_path}")
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
        if str(error).startswith("non-finite JSON number:"):
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
    if len(argv) < 2 or argv[0] != "--config" or argv[1].startswith("-"):
        raise ValueError(f"{label} argv_suffix must begin with --config and its input")
    return argv[1]


def _package_main_source(root: Path, entry_point: object) -> tuple[str, ast.Module]:
    entry_path, path = _required_path(root, entry_point, "entry_point")
    if not entry_path.startswith("experiment/code/") or not entry_path.endswith(".py"):
        raise ValueError("entry_point must be a package-manifest Python file")
    manifest, _manifest_bytes = _read_json_object(root, _PACKAGE_MANIFEST_PATH)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("package manifest files must be a list")
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
    return source, tree


def _module_name(entry_path: str) -> str:
    return entry_path.removesuffix(".py").replace("/", ".")


def _top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


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
    function: ast.FunctionDef, functions: Mapping[str, ast.FunctionDef]
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
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                target = functions.get(node.func.id)
                if target is not None:
                    queued.append(target)
    return nodes


def _has_size_proxy(nodes: list[ast.AST], aliases: Mapping[str, str]) -> bool:
    for node in nodes:
        if isinstance(node, ast.Attribute) and node.attr == "st_size":
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
    for function in _top_level_functions(tree).values():
        if re.search(r"(?:fallback|placeholder)", function.name, re.I) is None:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "evidence_eligible"
                    and isinstance(value, ast.Constant)
                    and value.value is True
                ):
                    return True
    return False


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
        if _has_size_proxy(_reachable_metric_nodes(function, functions), aliases):
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
    if contract["schema_version"] != 1:
        raise ValueError("package contract schema_version must equal 1")
    entry_point = contract["entry_point"]
    if not isinstance(entry_point, str):
        raise ValueError("entry_point must be text")
    source, tree = _package_main_source(project.root, entry_point)
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
    try:
        fixture_value = json.loads(fixture.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("self_test fixture must be JSON") from error
    if not isinstance(fixture_value, dict) or not fixture_value:
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
    if report["schema_version"] != 1 or report["passed"] is not True:
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
