"""Closed Stage-10 experiment-package and development self-test contracts."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .computational_package import validate_python_capability_safety
from .execution_environment import (
    ExecutionEnvironment,
    inspect_execution_environment,
    normalize_required_distributions,
)
from .models import ArtifactRef, ProjectState
from .paths import resolve_project_artifact
from .persistence import _fsync_directory, atomic_write_json
from .project import ResearchProject
from .transactions import project_mutation


EXPERIMENT_PACKAGE_CONTRACT_PATH = "experiment/package_contract.json"
SELF_TEST_REPORT_PATH = "experiment/self_test_report.json"
_PACKAGE_MANIFEST_PATH = "experiment/package_manifest.json"
_MAX_JSON_BYTES = 1024 * 1024
_MAX_FIXTURE_JSON_BYTES = 64 * 1024
_SELF_TEST_REGISTRATION_PENDING_PATH = (
    ".researchclaw/experiment-self-test-registration.pending.json"
)
_MAX_SELF_TEST_REGISTRATION_PENDING_BYTES = 16 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PACKAGE_KEYS = {
    "schema_version",
    "entry_point",
    "config_path",
    "result_path",
    "metrics",
    "self_test",
    "execution",
    "dependencies",
    "prohibitions",
}
METRIC_KEYS = {"name", "unit", "implementation"}
SELF_TEST_KEYS = {"argv_suffix", "fixture_path", "expected_metrics"}
_EXECUTION_KEYS = {"argv_suffix"}
_EXPECTED_METRIC_KEYS = {"name", "expected", "tolerance"}
_REPORT_KEYS = {
    "schema_version",
    "package_contract",
    "fixture",
    "environment_fingerprint",
    "package_manifest",
    "entry_point",
    "package_files",
    "metrics",
    "passed",
    "development_only",
}
_IDENTITY_KEYS = {"path", "sha256"}
_REPORT_METRIC_KEYS = {"name", "actual", "expected", "tolerance"}


@dataclass(frozen=True)
class ValidatedExperimentPackage:
    contract_sha256: str
    entry_point: str
    metric_entrypoints: Mapping[str, str]
    self_test_argv: tuple[str, ...]
    execution_argv: tuple[str, ...]
    required_distributions: tuple[str, ...]


@dataclass(frozen=True)
class SelfTestPreparationStatus:
    """Complete pre-approval argv for one externally run known-answer test."""

    argv: tuple[str, ...]
    environment_fingerprint: str
    package_contract_sha256: str
    report_path: str
    registration_argv: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": "ready_for_explicit_self_test",
            "argv": list(self.argv),
            "environment_fingerprint": self.environment_fingerprint,
            "package_contract_sha256": self.package_contract_sha256,
            "report_path": self.report_path,
            "registration_argv": list(self.registration_argv),
        }


@dataclass(frozen=True)
class _PendingSelfTestRegistration:
    project_id: str
    artifact: ArtifactRef
    event_log_size: int
    event_log_prefix_sha256: str
    prior_state_sha256: str
    target_state_sha256: str
    target_next_action: str
    event: object

    def to_dict(self) -> dict[str, object]:
        from .events import EvaluationEvent

        if not isinstance(self.event, EvaluationEvent):
            raise ValueError("experiment_self_test_registration_recovery_invalid")
        return {
            "schema_version": 1,
            "project_id": self.project_id,
            "artifact": {
                "path": self.artifact.path,
                "sha256": self.artifact.sha256,
                "size": self.artifact.size,
            },
            "event_log_size": self.event_log_size,
            "event_log_prefix_sha256": self.event_log_prefix_sha256,
            "prior_state_sha256": self.prior_state_sha256,
            "target_state_sha256": self.target_state_sha256,
            "target_next_action": self.target_next_action,
            "event": self.event.to_dict(),
        }


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
        if str(error).startswith(
            ("non-finite JSON number:", "JSON keys must be unique")
        ):
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
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


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
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
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
    root: Path,
    entry_point: object,
    *,
    manifest_path: str = _PACKAGE_MANIFEST_PATH,
    code_root: str = "experiment/code/",
) -> tuple[str, ast.Module, str, str]:
    entry_path, path = _required_path(root, entry_point, "entry_point")
    if not entry_path.startswith(code_root) or not entry_path.endswith(".py"):
        raise ValueError("entry_point must be a package-manifest Python file")
    manifest, manifest_bytes = _read_json_object(root, manifest_path)
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
        _path, declared_file = _required_path(
            root, relative_path, "package manifest file"
        )
        if hashlib.sha256(declared_file.read_bytes()).hexdigest() != declared_sha256:
            raise ValueError(
                "package manifest identity does not match its declared file"
            )
    entries = [
        item
        for item in files
        if isinstance(item, dict) and item.get("path") == entry_path
    ]
    if len(entries) != 1 or set(entries[0]) - {"path", "role", "sha256"}:
        raise ValueError("entry_point must be declared once by the package manifest")
    expected_hash = entries[0].get("sha256")
    source_bytes = path.read_bytes()
    if (
        not isinstance(expected_hash, str)
        or hashlib.sha256(source_bytes).hexdigest() != expected_hash
    ):
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


class _LexicalScopeNodes(ast.NodeVisitor):
    """Collect one function's nodes without crossing into a nested lexical scope."""

    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.nodes.append(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.nodes.append(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.nodes.append(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.nodes.append(node)


def _lexical_scope_nodes(function: ast.FunctionDef) -> list[ast.AST]:
    collector = _LexicalScopeNodes()
    for statement in function.body:
        collector.visit(statement)
    return collector.nodes


def _function_aliases(
    tree: ast.Module, functions: Mapping[str, ast.FunctionDef]
) -> dict[str, str]:
    """Resolve only ordered module-scope aliases to known local callables."""
    aliases: dict[str, str] = {}
    alias_targets: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target_names = (
            [target.id for target in node.targets if isinstance(target, ast.Name)]
            if isinstance(node, ast.Assign)
            else [node.target.id]
            if isinstance(node.target, ast.Name)
            else []
        )
        if any(target in alias_targets for target in target_names):
            raise ValueError("callable alias is ambiguous or reassigned")
        if not isinstance(node.value, ast.Name):
            continue
        value_name = node.value.id
        resolved = aliases.get(value_name, value_name)
        if resolved in functions and getattr(
            functions[resolved], "lineno", 0
        ) >= getattr(node, "lineno", 0):
            raise ValueError("callable alias is defined before its target")
        if resolved in functions or resolved == "dict":
            aliases.update({target: resolved for target in target_names})
            alias_targets.update(target_names)
    return aliases


def _local_call_name(node: ast.Call, aliases: Mapping[str, str]) -> str | None:
    if not isinstance(node.func, ast.Name):
        return None
    return aliases.get(node.func.id, node.func.id)


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> tuple[ast.AST, ...]:
    return tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)


def _local_alias_target(
    function: ast.FunctionDef, call: ast.Call
) -> tuple[str | None, bool]:
    """Resolve a local callable alias using only source-order-reachable definitions."""
    if not isinstance(call.func, ast.Name):
        return None, False

    assignments = sorted(
        [
            node
            for node in _lexical_scope_nodes(function)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ],
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )

    def resolve(name: str, before: tuple[int, int], seen: set[str]) -> tuple[str, bool]:
        all_definitions = [
            node
            for node in assignments
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in _assignment_targets(node)
            )
        ]
        definitions = [
            node
            for node in all_definitions
            if (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)) < before
        ]
        if not definitions:
            if all_definitions:
                raise ValueError("callable alias is used before its definition")
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

    return resolve(
        call.func.id,
        (getattr(call, "lineno", 0), getattr(call, "col_offset", 0)),
        set(),
    )


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for imported in node.names:
                aliases[imported.asname or imported.name.split(".")[0]] = imported.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for imported in node.names:
                aliases[
                    imported.asname or imported.name
                ] = f"{node.module}.{imported.name}"
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


def _resolved_local_call_name(
    function: ast.FunctionDef,
    call: ast.Call,
    functions: Mapping[str, ast.FunctionDef],
    function_aliases: Mapping[str, str],
) -> str | None:
    target_name, local_alias = _local_alias_target(function, call)
    if target_name is None or not local_alias:
        return _local_call_name(call, function_aliases)
    if target_name not in functions and target_name != "dict":
        raise ValueError("callable alias is unresolved or ambiguous")
    return target_name


def _reachable_local_functions(
    function: ast.FunctionDef,
    functions: Mapping[str, ast.FunctionDef],
    function_aliases: Mapping[str, str],
) -> list[ast.FunctionDef]:
    reachable: list[ast.FunctionDef] = []
    queued = [function]
    visited: set[str] = set()
    while queued:
        current = queued.pop()
        if current.name in visited:
            continue
        visited.add(current.name)
        reachable.append(current)
        current_nodes = _lexical_scope_nodes(current)
        if any(
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef),
            )
            for node in current_nodes
        ):
            raise ValueError("reachable function must not define a nested callable")
        for node in current_nodes:
            if isinstance(node, ast.Call):
                target_name = _resolved_local_call_name(
                    current, node, functions, function_aliases
                )
                target = functions.get(target_name or "")
                if target is not None:
                    queued.append(target)
    return reachable


def _reachable_metric_nodes(
    function: ast.FunctionDef,
    functions: Mapping[str, ast.FunctionDef],
    function_aliases: Mapping[str, str],
) -> list[ast.AST]:
    return [
        node
        for reachable in _reachable_local_functions(
            function, functions, function_aliases
        )
        for node in _lexical_scope_nodes(reachable)
    ]


def _reachable_called_function_nodes(
    function: ast.FunctionDef,
    initial_nodes: list[ast.AST],
    functions: Mapping[str, ast.FunctionDef],
    function_aliases: Mapping[str, str],
) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for call in (node for node in initial_nodes if isinstance(node, ast.Call)):
        target_name = _resolved_local_call_name(
            function, call, functions, function_aliases
        )
        target = functions.get(target_name or "")
        if target is not None:
            nodes.extend(_reachable_metric_nodes(target, functions, function_aliases))
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
        for reachable in _reachable_local_functions(
            function, functions, function_aliases
        ):
            for node in _lexical_scope_nodes(reachable):
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
                target_name = _resolved_local_call_name(
                    reachable, node, functions, function_aliases
                )
                if target_name == "dict" and any(
                    keyword.arg == "evidence_eligible"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
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


def _is_literal_path_text_write(call: ast.Call, path: str) -> bool:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "write_text":
        return False
    target = call.func.value
    return (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Name)
        and target.func.id == "Path"
        and len(target.args) == 1
        and isinstance(target.args[0], ast.Constant)
        and target.args[0].value == path
    )


def _is_self_test_report_write(
    call: ast.Call, report_path: str = SELF_TEST_REPORT_PATH
) -> bool:
    return _is_literal_path_text_write(call, report_path)


_MUTATING_METHODS = {
    "chmod",
    "dump",
    "mkdir",
    "rename",
    "replace",
    "rmdir",
    "save",
    "savefig",
    "symlink_to",
    "hardlink_to",
    "to_csv",
    "to_json",
    "to_parquet",
    "to_pickle",
    "touch",
    "truncate",
    "unlink",
    "write",
    "write_bytes",
    "write_text",
    "writelines",
}
_MUTATING_CALLS = {
    "os.chmod",
    "os.makedirs",
    "os.mkdir",
    "os.remove",
    "os.rename",
    "os.replace",
    "os.rmdir",
    "os.symlink",
    "os.unlink",
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
}


def _open_call_may_write(call: ast.Call, aliases: Mapping[str, str]) -> bool:
    name = _dotted_name(call.func, aliases)
    operation = call.func.attr if isinstance(call.func, ast.Attribute) else name
    if operation != "open":
        return False
    mode_node: ast.AST | None = None
    mode_index = 1 if name in {"open", "builtins.open", "io.open"} else 0
    if len(call.args) > mode_index:
        mode_node = call.args[mode_index]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
    if mode_node is None:
        return False
    return not (
        isinstance(mode_node, ast.Constant)
        and isinstance(mode_node.value, str)
        and not any(marker in mode_node.value for marker in "wax+")
    )


def _call_may_mutate_filesystem(
    call: ast.Call,
    aliases: Mapping[str, str],
    *,
    scope_nodes: list[ast.AST] = (),
) -> bool:
    name = _dotted_name(call.func, aliases)
    operation = call.func.attr if isinstance(call.func, ast.Attribute) else name
    if operation in _MUTATING_METHODS:
        return True
    if name in _MUTATING_CALLS or (
        name is not None and (name.startswith("shutil.copy") or name == "shutil.move")
    ):
        return True
    if name == "os.open":
        return not _is_readonly_current_interpreter_open(call, scope_nodes)
    if operation == "open":
        return _open_call_may_write(call, aliases)
    return name in {"json.dump", "dump"} or (
        name in {"print", "builtins.print"}
        and any(keyword.arg == "file" for keyword in call.keywords)
    )


def _is_current_interpreter_path(node: ast.AST) -> bool:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        and len(node.args) == 0
        and len(node.keywords) == 1
        and node.keywords[0].arg == "strict"
        and isinstance(node.keywords[0].value, ast.Constant)
        and node.keywords[0].value.value is True
    ):
        return False
    path_call = node.func.value
    return (
        isinstance(path_call, ast.Call)
        and isinstance(path_call.func, ast.Name)
        and path_call.func.id == "Path"
        and len(path_call.args) == 1
        and isinstance(path_call.args[0], ast.Attribute)
        and isinstance(path_call.args[0].value, ast.Name)
        and path_call.args[0].value.id == "sys"
        and path_call.args[0].attr == "executable"
    )


def _is_base_interpreter_path(node: ast.AST) -> bool:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        and len(node.args) == 0
        and len(node.keywords) == 1
        and node.keywords[0].arg == "strict"
        and isinstance(node.keywords[0].value, ast.Constant)
        and node.keywords[0].value.value is True
    ):
        return False
    path_call = node.func.value
    return (
        isinstance(path_call, ast.Call)
        and isinstance(path_call.func, ast.Name)
        and path_call.func.id == "Path"
        and len(path_call.args) == 1
        and isinstance(path_call.args[0], ast.Attribute)
        and isinstance(path_call.args[0].value, ast.Name)
        and path_call.args[0].value.id == "sys"
        and path_call.args[0].attr == "_base_executable"
    )


def _is_process_image_path(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execution_environment_process_image"
        and not node.args
        and not node.keywords
    )


def _readonly_os_open_flags(node: ast.AST) -> frozenset[str] | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _readonly_os_open_flags(node.left)
        right = _readonly_os_open_flags(node.right)
        if left is None or right is None or left & right:
            return None
        return left | right
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
        and node.attr in {"O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW"}
    ):
        return frozenset({node.attr})
    return None


_READONLY_OS_OPEN_ATTRIBUTES = frozenset({"O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW"})


def _os_capability_target(node: ast.AST) -> bool:
    """Whether a target can change the collector's trusted ``os`` capability."""
    if isinstance(node, ast.Name):
        return node.id == "os"
    if isinstance(node, ast.Attribute):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and (node.attr == "open" or node.attr.startswith("O_"))
        )
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_os_capability_target(item) for item in node.elts)
    return False


def _nodes_rebind_os_capabilities(nodes: list[ast.AST]) -> bool:
    """Reject lexical writes/import aliases that invalidate the approved open call."""
    for node in nodes:
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == "os"
        ):
            return True
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and _os_capability_target(node)
        ):
            return True
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == "os"
        ):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
            _os_capability_target(target) for target in _assignment_targets(node)
        ):
            return True
        if isinstance(node, ast.AugAssign) and _os_capability_target(node.target):
            return True
        if isinstance(node, ast.NamedExpr) and _os_capability_target(node.target):
            return True
        if isinstance(node, ast.Delete) and any(
            _os_capability_target(target) for target in node.targets
        ):
            return True
        if isinstance(node, ast.Import) and any(
            imported.asname == "os"
            or (
                imported.name != "os"
                and _import_binding(imported, from_import=False) == "os"
            )
            for imported in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and any(
            _import_binding(imported, from_import=True) == "os"
            for imported in node.names
        ):
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == "os":
            return True
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ) and any(
            argument.arg == "os"
            for argument in [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
                *([node.args.vararg] if node.args.vararg is not None else []),
                *([node.args.kwarg] if node.args.kwarg is not None else []),
            ]
        ):
            return True
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "os":
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == "os":
            return True
    return False


_ATTESTATION_CALL_COUNTS = {
    "ctypes.CDLL": 2,
    "ctypes.byref": 2,
    "ctypes.c_uint32": 1,
    "ctypes.create_string_buffer": 2,
    "libproc.proc_pidpath": 1,
    "libsystem._NSGetExecutablePath": 2,
    "os.fsdecode": 2,
    "os.getpid": 1,
    "os.readlink": 1,
}
_ATTESTATION_ATTRIBUTES = {
    ("ctypes", "CDLL"),
    ("ctypes", "byref"),
    ("ctypes", "c_uint32"),
    ("ctypes", "create_string_buffer"),
    ("libproc", "proc_pidpath"),
    ("libsystem", "_NSGetExecutablePath"),
}


def _validate_current_process_attestation(tree: ast.Module) -> None:
    """Confine native process attestation to the canonical read-only collector."""
    ctypes_imports = [
        (node, imported)
        for node in tree.body
        if isinstance(node, ast.Import)
        for imported in node.names
        if imported.name == "ctypes"
    ]
    if (
        len(ctypes_imports) != 1
        or ctypes_imports[0][1].asname is not None
        or len(ctypes_imports[0][0].names) != 1
    ):
        raise ValueError("self-test adapter process attestation is invalid")
    function = _top_level_functions(tree).get("execution_environment_process_image")
    if function is None:
        raise ValueError("self-test adapter process attestation is invalid")
    function_nodes = set(ast.walk(function))
    aliases = _import_aliases(tree)
    observed_calls = {name: [] for name in _ATTESTATION_CALL_COUNTS}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            sensitive_attribute = (node.value.id, node.attr)
            if node.value.id in {"ctypes", "libproc", "libsystem"}:
                if (
                    node not in function_nodes
                    or sensitive_attribute not in _ATTESTATION_ATTRIBUTES
                ):
                    raise ValueError("self-test adapter process attestation is invalid")
        if not isinstance(node, ast.Call):
            continue
        call_name = _dotted_name(node.func, aliases)
        if call_name in observed_calls:
            if node not in function_nodes:
                raise ValueError("self-test adapter process attestation is invalid")
            observed_calls[call_name].append(node)
        elif call_name is not None and call_name.startswith(
            ("ctypes.", "libproc.", "libsystem.")
        ):
            raise ValueError("self-test adapter process attestation is invalid")
    if any(
        len(observed_calls[name]) != count
        for name, count in _ATTESTATION_CALL_COUNTS.items()
    ):
        raise ValueError("self-test adapter process attestation is invalid")
    library_calls = observed_calls["ctypes.CDLL"]
    if {
        (
            call.args[0].value
            if len(call.args) == 1 and isinstance(call.args[0], ast.Constant)
            else object()
        )
        for call in library_calls
        if len(call.keywords) == 1
        and call.keywords[0].arg == "use_errno"
        and isinstance(call.keywords[0].value, ast.Constant)
        and call.keywords[0].value.value is True
    } != {"/usr/lib/libproc.dylib", None}:
        raise ValueError("self-test adapter process attestation is invalid")
    readlink_call = observed_calls["os.readlink"][0]
    if not (
        len(readlink_call.args) == 1
        and isinstance(readlink_call.args[0], ast.Constant)
        and readlink_call.args[0].value == "/proc/self/exe"
        and not readlink_call.keywords
    ):
        raise ValueError("self-test adapter process attestation is invalid")
    expected_libraries = {
        "libproc": "/usr/lib/libproc.dylib",
        "libsystem": None,
    }
    for name, expected_library in expected_libraries.items():
        assignments = [
            node
            for node in function_nodes
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in _assignment_targets(node)
            )
        ]
        if len(assignments) != 1:
            raise ValueError("self-test adapter process attestation is invalid")
        value = assignments[0].value
        if not (
            isinstance(value, ast.Call)
            and _dotted_name(value.func, aliases) == "ctypes.CDLL"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and value.args[0].value == expected_library
            and len(value.keywords) == 1
            and value.keywords[0].arg == "use_errno"
            and isinstance(value.keywords[0].value, ast.Constant)
            and value.keywords[0].value.value is True
        ):
            raise ValueError("self-test adapter process attestation is invalid")


def _is_readonly_current_interpreter_open(
    call: ast.Call, scope_nodes: list[ast.AST]
) -> bool:
    if _nodes_rebind_os_capabilities(scope_nodes):
        return False
    if len(call.args) != 2 or call.keywords:
        return False
    path, flags = call.args
    approved_assignments = {
        "interpreter": _is_current_interpreter_path,
        "base_interpreter": _is_base_interpreter_path,
        "process_image": _is_process_image_path,
    }
    if isinstance(path, ast.Name) and path.id in approved_assignments:
        interpreter_assignments = [
            node.value
            for node in scope_nodes
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name) and target.id == path.id
                for target in _assignment_targets(node)
            )
        ]
        if len(interpreter_assignments) != 1 or not approved_assignments[path.id](
            interpreter_assignments[0]
        ):
            return False
    elif not _is_current_interpreter_path(path):
        return False
    return _readonly_os_open_flags(flags) == frozenset(
        {"O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW"}
    )


def _import_binding(imported: ast.alias, *, from_import: bool) -> str:
    if imported.asname is not None:
        return imported.asname
    return imported.name if from_import else imported.name.split(".")[0]


def _nodes_bind_path(nodes: list[ast.AST]) -> bool:
    for node in nodes:
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "Path"
        ):
            return True
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == "Path"
        ):
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            _import_binding(imported, from_import=isinstance(node, ast.ImportFrom))
            == "Path"
            for imported in node.names
        ):
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == "Path":
            return True
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "Path":
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == "Path":
            return True
    return False


def _function_binds_path(function: ast.FunctionDef) -> bool:
    parameters = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
        *([function.args.vararg] if function.args.vararg is not None else []),
        *([function.args.kwarg] if function.args.kwarg is not None else []),
    ]
    return any(parameter.arg == "Path" for parameter in parameters) or _nodes_bind_path(
        _lexical_scope_nodes(function)
    )


def _has_unambiguous_path_binding(
    tree: ast.Module, reachable_functions: list[ast.FunctionDef]
) -> bool:
    approved_imports = [
        imported
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "pathlib"
        and node.level == 0
        for imported in node.names
        if imported.name == "Path" and imported.asname is None
    ]
    noncanonical_import = any(
        _import_binding(imported, from_import=isinstance(node, ast.ImportFrom))
        == "Path"
        and not (
            isinstance(node, ast.ImportFrom)
            and node.module == "pathlib"
            and node.level == 0
            and imported.name == "Path"
            and imported.asname is None
        )
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for imported in node.names
    )
    collector = _LexicalScopeNodes()
    for statement in tree.body:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        collector.visit(statement)
    return (
        len(approved_imports) == 1
        and not noncanonical_import
        and not _nodes_bind_path(collector.nodes)
        and not any(_function_binds_path(function) for function in reachable_functions)
    )


def _has_ambiguous_writer_alias(
    tree: ast.Module,
    reachable_nodes: list[ast.AST],
    aliases: Mapping[str, str],
) -> bool:
    for node in [*tree.body, *reachable_nodes]:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = _dotted_name(node.value, aliases)
        if target in {"open", "builtins.open", "Path", "pathlib.Path"}:
            return True
    return False


def _validate_exclusive_artifact_writers(
    tree: ast.Module,
    reachable_functions: list[ast.FunctionDef],
    branch_nodes: list[ast.AST],
    reachable_nodes: list[ast.AST],
    *,
    report_path: str = SELF_TEST_REPORT_PATH,
    result_path: str = "experiment/results.json",
) -> None:
    """Require the checked-in adapter's two exclusive literal artifact writers."""
    aliases = _import_aliases(tree)
    mutation_calls = [
        node
        for node in reachable_nodes
        if isinstance(node, ast.Call)
        and _call_may_mutate_filesystem(
            node, aliases, scope_nodes=[*tree.body, *reachable_nodes]
        )
    ]
    report_writes = [
        node for node in mutation_calls if _is_self_test_report_write(node, report_path)
    ]
    result_writes = [
        node
        for node in mutation_calls
        if _is_literal_path_text_write(node, result_path)
    ]
    approved = {*report_writes, *result_writes}
    if (
        not _has_unambiguous_path_binding(tree, reachable_functions)
        or _has_ambiguous_writer_alias(tree, reachable_nodes, aliases)
        or len(report_writes) != 1
        or report_writes[0] not in branch_nodes
        or len(result_writes) != 1
        or result_writes[0] in branch_nodes
        or any(node not in approved for node in mutation_calls)
    ):
        raise ValueError(
            "self-test adapter must use only its exclusive canonical artifact writers"
        )


def _self_test_report_payload_name(
    call: ast.Call, report_path: str = SELF_TEST_REPORT_PATH
) -> str | None:
    if not _is_self_test_report_write(call, report_path):
        return None
    if not call.args:
        return None
    payload = call.args[0]
    serializer = (
        payload.left
        if isinstance(payload, ast.BinOp) and isinstance(payload.op, ast.Add)
        else payload
    )
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


def _mapping_is_mutated(nodes: list[ast.AST]) -> bool:
    literal_mapping_names = {
        target.id
        for node in nodes
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(getattr(node, "value", None), ast.Dict)
        for target in _assignment_targets(node)
        if isinstance(target, ast.Name)
    }
    for node in nodes:
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
            and node.func.attr
            in {"update", "setdefault", "clear", "pop", "popitem", "__ior__"}
            and (
                not isinstance(node.func.value, ast.Name)
                or node.func.value.id in literal_mapping_names
            )
        ):
            return True
    return False


def _validate_self_test_adapter(
    tree: ast.Module,
    metric_entrypoints: Mapping[str, str],
    *,
    report_path: str = SELF_TEST_REPORT_PATH,
    result_path: str = "experiment/results.json",
) -> None:
    """Prove that the written self-test report carries declared metric values."""
    if _nodes_rebind_os_capabilities(list(ast.walk(tree))):
        raise ValueError(
            "self-test adapter must use only its exclusive canonical artifact writers"
        )
    main = _top_level_functions(tree).get("main")
    if main is None:
        raise ValueError("self-test adapter requires a top-level main function")
    functions = _top_level_functions(tree)
    function_aliases = _function_aliases(tree, functions)
    main_nodes = _lexical_scope_nodes(main)
    branches = [
        node
        for node in main_nodes
        if isinstance(node, ast.If) and _is_positive_self_test_condition(node.test)
    ]
    mentioned_branches = [
        node
        for node in main_nodes
        if isinstance(node, ast.If) and _mentions_self_test(node.test)
    ]
    if len(branches) != 1 or len(mentioned_branches) != 1:
        raise ValueError(
            "self-test adapter must have one unambiguous --self-test branch"
        )
    nodes = [item for statement in branches[0].body for item in ast.walk(statement)]
    if any(
        isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try))
        for node in nodes
    ):
        raise ValueError("self-test adapter must not use ambiguous provenance branches")
    reachable_functions = _reachable_local_functions(main, functions, function_aliases)
    all_nodes = [
        node
        for function in reachable_functions
        for node in _lexical_scope_nodes(function)
    ]
    _validate_exclusive_artifact_writers(
        tree,
        reachable_functions,
        nodes,
        all_nodes,
        report_path=report_path,
        result_path=result_path,
    )
    writes = [
        (node, _self_test_report_payload_name(node, report_path))
        for node in all_nodes
        if isinstance(node, ast.Call) and _is_self_test_report_write(node, report_path)
    ]
    if len(writes) != 1 or writes[0][0] not in nodes or writes[0][1] is None:
        raise ValueError("self-test adapter must write exactly one self-test report")
    write, report_name = writes[0]
    assert report_name is not None
    write_position = (getattr(write, "lineno", 0), getattr(write, "col_offset", 0))
    before_write_nodes = [
        node
        for node in nodes
        if (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)) < write_position
    ]
    called_nodes = _reachable_called_function_nodes(
        main, before_write_nodes, functions, function_aliases
    )
    if _mapping_is_mutated([*before_write_nodes, *called_nodes]):
        raise ValueError("self-test adapter rejects mutable report provenance")
    write_line = getattr(write, "lineno", 0)
    assignments = sorted(
        [
            node
            for node in nodes
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and getattr(node, "lineno", 0) < write_line
        ],
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )
    report_definitions = [
        node
        for node in assignments
        if any(
            isinstance(target, ast.Name) and target.id == report_name
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
        )
    ]
    if len(report_definitions) != 1 or not isinstance(
        report_definitions[0].value, ast.Dict
    ):
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
            record
            for record in selected_records
            if _dict_fields(record).get("name")
            and isinstance(_dict_fields(record)["name"], ast.Constant)
            and _dict_fields(record)["name"].value == metric_name
        ]
        if (
            len(matching) != 1
            or _metric_source(
                _dict_fields(matching[0]).get("actual", ast.Constant(None)),
                scalars,
                mappings,
            )
            != function_name
        ):
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
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(unit, str)
            or not unit
        ):
            raise ValueError("metric name and unit must be non-empty strings")
        if name in metrics:
            raise ValueError("metric names must be unique")
        if not isinstance(implementation, str) or not implementation.startswith(
            f"{module}:"
        ):
            raise ValueError(
                "metric implementation must bind to the package entry_point"
            )
        function_name = implementation.partition(":")[2]
        function = functions.get(function_name)
        if function is None:
            raise ValueError(
                "metric implementation must resolve to a top-level function"
            )
        if _has_size_proxy(
            _reachable_metric_nodes(function, functions, function_aliases), aliases
        ):
            raise ValueError(
                "metric implementation must not use an input or file size proxy"
            )
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


def _reject_module_scope_lambdas(tree: ast.Module) -> None:
    class ModuleExecutionVisitor(ast.NodeVisitor):
        def visit_Lambda(self, _node: ast.Lambda) -> None:
            raise ValueError("entry_point must not define a module-scope lambda")

        def _visit_function_definition(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> None:
            # The body is a separate lexical scope. Definitions' decorators,
            # defaults, and annotations are nevertheless evaluated by the
            # module execution that creates the function.
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            if node.returns is not None:
                self.visit(node.returns)
            for type_parameter in getattr(node, "type_params", ()):
                self.visit(type_parameter)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function_definition(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function_definition(node)

    ModuleExecutionVisitor().visit(tree)


def validate_experiment_package_contract(
    project: ResearchProject
) -> ValidatedExperimentPackage:
    """Validate the non-executing closed package contract for a project."""
    return validate_experiment_package_contract_at(
        project,
        package_root=project.root,
        contract_path=EXPERIMENT_PACKAGE_CONTRACT_PATH,
    )


def validate_experiment_package_contract_at(
    project: ResearchProject,
    *,
    package_root: Path,
    contract_path: str,
) -> ValidatedExperimentPackage:
    """Validate a closed package rooted beneath ``package_root`` without execution."""
    del (
        project
    )  # The rooted contract is intentionally independent of live project files.
    package_root = Path(package_root)
    baseline_layout = contract_path == EXPERIMENT_PACKAGE_CONTRACT_PATH
    manifest_path = (
        _PACKAGE_MANIFEST_PATH
        if baseline_layout
        else "package_metadata/package_manifest.json"
    )
    code_root = "experiment/code/" if baseline_layout else "code/"
    expected_result = "experiment/results.json" if baseline_layout else "results.json"
    report_path = (
        SELF_TEST_REPORT_PATH
        if baseline_layout
        else "package_metadata/self_test_report.json"
    )
    contract, contract_bytes = _read_json_object(package_root, contract_path)
    _require_closed(contract, PACKAGE_KEYS, "package contract")
    if not _schema_version_one(contract["schema_version"]):
        raise ValueError("package contract schema_version must equal 1")
    entry_point = contract["entry_point"]
    if not isinstance(entry_point, str):
        raise ValueError("entry_point must be text")
    source, tree, _manifest_sha256, _entry_point_sha256 = _package_main_source(
        package_root,
        entry_point,
        manifest_path=manifest_path,
        code_root=code_root,
    )
    _validate_current_process_attestation(tree)
    _reject_module_scope_lambdas(tree)
    config_path, _config = _required_path(
        package_root, contract["config_path"], "config_path"
    )
    result_path = contract["result_path"]
    if result_path != expected_result:
        raise ValueError(f"result_path must be {expected_result}")
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
    _required_path(package_root, self_test_config, "self_test input")
    if execution_config != config_path or self_test_config == execution_config:
        raise ValueError("self-test and research inputs must be distinct")
    fixture_path, fixture = _required_path(
        package_root, self_test["fixture_path"], "self_test fixture"
    )
    if fixture_path in {config_path, self_test_config} or fixture.stat().st_size == 0:
        raise ValueError("self_test fixture must be a non-empty distinct input")
    fixture_value, _fixture_bytes = _read_json_object(
        package_root,
        fixture_path,
        maximum_bytes=_MAX_FIXTURE_JSON_BYTES,
        label="fixture",
    )
    if not fixture_value:
        raise ValueError("self_test fixture must be non-empty")
    if not isinstance(contract["dependencies"], list):
        raise ValueError("dependencies must be a string list")
    try:
        required_distributions = normalize_required_distributions(
            tuple(contract["dependencies"])
        )
    except ValueError as error:
        raise ValueError("dependencies must be a closed string list") from error
    if list(required_distributions) != contract["dependencies"]:
        raise ValueError("dependencies must be normalized, sorted, and unique")
    if not isinstance(contract["prohibitions"], dict) or any(
        not isinstance(key, str) or value is not False
        for key, value in contract["prohibitions"].items()
    ):
        raise ValueError("prohibitions must be false-valued declarations")
    metrics, _expected = _validate_metrics(
        contract["metrics"], self_test["expected_metrics"], entry_point, tree
    )
    _validate_self_test_adapter(
        tree,
        metrics,
        report_path=report_path,
        result_path=expected_result,
    )
    if validate_python_capability_safety(
        entry_point, source, allow_current_process_attestation=True
    ):
        raise ValueError("entry_point has a prohibited static capability")
    return ValidatedExperimentPackage(
        contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
        entry_point=entry_point,
        metric_entrypoints=MappingProxyType(metrics),
        self_test_argv=self_test_argv,
        execution_argv=execution_argv,
        required_distributions=required_distributions,
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


def _validate_package_file_identities(
    value: object, expected: list[dict[str, str]]
) -> None:
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
    project: ResearchProject,
    package: ValidatedExperimentPackage,
    *,
    environment: ExecutionEnvironment | None = None,
) -> ArtifactRef:
    """Validate an externally produced self-test report without recording it."""
    current = validate_experiment_package_contract(project)
    if current != package:
        raise ValueError("package changed since self-test validation")
    contract, _contract_bytes = _read_json_object(
        project.root, EXPERIMENT_PACKAGE_CONTRACT_PATH
    )
    self_test = _require_closed(contract["self_test"], SELF_TEST_KEYS, "self_test")
    fixture_path, fixture = _required_path(
        project.root, self_test["fixture_path"], "self_test fixture"
    )
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
        report["fixture"],
        fixture_path,
        hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "fixture",
    )
    fingerprint = report["environment_fingerprint"]
    if not isinstance(fingerprint, str) or _SHA256.fullmatch(fingerprint) is None:
        raise ValueError("environment fingerprint must be an opaque lowercase SHA-256")
    if environment is None:
        environment = inspect_execution_environment(
            Path(sys.executable).resolve(strict=True), package.required_distributions
        )
    if fingerprint != environment.fingerprint:
        raise ValueError("self_test environment fingerprint does not match")
    _metrics, expected = _validate_metrics(
        contract["metrics"],
        self_test["expected_metrics"],
        contract["entry_point"],
        _package_main_source(project.root, contract["entry_point"])[1],
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
        if not all(
            _finite_number(metric[field])
            for field in ("actual", "expected", "tolerance")
        ):
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


def _self_test_registration_pending_path(project: ResearchProject) -> Path:
    return project.root / _SELF_TEST_REGISTRATION_PENDING_PATH


def _state_sha256(state: ProjectState) -> str:
    payload = json.dumps(
        state.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _persist_self_test_registration_pending(
    project: ResearchProject, pending: _PendingSelfTestRegistration
) -> None:
    payload = pending.to_dict()
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_SELF_TEST_REGISTRATION_PENDING_BYTES:
        raise ValueError("experiment_self_test_registration_recovery_invalid")
    atomic_write_json(
        _self_test_registration_pending_path(project),
        payload,
        prefix="experiment-self-test-registration-",
        compact=True,
    )


def _clear_self_test_registration_pending(project: ResearchProject) -> None:
    path = _self_test_registration_pending_path(project)
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _read_self_test_registration_pending(project: ResearchProject) -> bytes:
    path = _self_test_registration_pending_path(project)
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > _MAX_SELF_TEST_REGISTRATION_PENDING_BYTES
        ):
            raise ValueError("pending self-test registration is invalid")
        chunks: list[bytes] = []
        remaining = _MAX_SELF_TEST_REGISTRATION_PENDING_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > _MAX_SELF_TEST_REGISTRATION_PENDING_BYTES:
            raise ValueError("pending self-test registration is too large")
        return payload
    finally:
        os.close(descriptor)


def _load_self_test_registration_pending(
    project: ResearchProject,
) -> _PendingSelfTestRegistration | None:
    path = _self_test_registration_pending_path(project)
    if not os.path.lexists(path):
        return None
    try:
        raw = json.loads(
            _read_self_test_registration_pending(project).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _raw: (_ for _ in ()).throw(
                ValueError("pending self-test registration numbers must be finite")
            ),
        )
        fields = {
            "schema_version",
            "project_id",
            "artifact",
            "event_log_size",
            "event_log_prefix_sha256",
            "prior_state_sha256",
            "target_state_sha256",
            "target_next_action",
            "event",
        }
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValueError("pending self-test registration must be closed")
        artifact_raw = raw["artifact"]
        event_raw = raw["event"]
        if (
            not isinstance(raw["schema_version"], int)
            or isinstance(raw["schema_version"], bool)
            or raw["schema_version"] != 1
            or not isinstance(raw["project_id"], str)
            or not raw["project_id"]
            or not isinstance(artifact_raw, dict)
            or set(artifact_raw) != {"path", "sha256", "size"}
            or artifact_raw["path"] != SELF_TEST_REPORT_PATH
            or not isinstance(artifact_raw["sha256"], str)
            or _SHA256.fullmatch(artifact_raw["sha256"]) is None
            or not isinstance(artifact_raw["size"], int)
            or isinstance(artifact_raw["size"], bool)
            or artifact_raw["size"] < 0
            or not isinstance(raw["event_log_size"], int)
            or isinstance(raw["event_log_size"], bool)
            or raw["event_log_size"] < 0
            or not isinstance(raw["event_log_prefix_sha256"], str)
            or _SHA256.fullmatch(raw["event_log_prefix_sha256"]) is None
            or not isinstance(raw["prior_state_sha256"], str)
            or _SHA256.fullmatch(raw["prior_state_sha256"]) is None
            or not isinstance(raw["target_state_sha256"], str)
            or _SHA256.fullmatch(raw["target_state_sha256"]) is None
            or raw["target_next_action"]
            not in {"approve_experiment_execution", "report_missing_execution_inputs"}
            or not isinstance(event_raw, dict)
            or set(event_raw)
            != {"schema_version", "timestamp", "type", "project_id", "payload"}
        ):
            raise ValueError("pending self-test registration identity is invalid")
        from .events import EvaluationEvent

        artifact = ArtifactRef(
            path=artifact_raw["path"],
            sha256=artifact_raw["sha256"],
            size=artifact_raw["size"],
        )
        event = EvaluationEvent.from_dict(event_raw)
        expected_payload = {
            "path": artifact.path,
            "sha256": artifact.sha256,
            "size": artifact.size,
        }
        if (
            raw["project_id"] != project.state.project_id
            or event.project_id != raw["project_id"]
            or event.type != "experiment_self_test_registered"
            or not isinstance(event.payload.get("size"), int)
            or isinstance(event.payload.get("size"), bool)
            or event.payload != expected_payload
        ):
            raise ValueError("pending self-test registration binding is invalid")
        current_identity = _state_sha256(project.state)
        if current_identity == raw["prior_state_sha256"]:
            target_state = replace(
                project.state,
                next_action=raw["target_next_action"],
                artifacts={
                    **project.state.artifacts,
                    SELF_TEST_REPORT_PATH: artifact,
                },
            )
            if _state_sha256(target_state) != raw["target_state_sha256"]:
                raise ValueError("pending self-test registration state is invalid")
        elif current_identity == raw["target_state_sha256"]:
            if (
                project.state.next_action != raw["target_next_action"]
                or project.state.artifacts.get(SELF_TEST_REPORT_PATH) != artifact
            ):
                raise ValueError("pending self-test registration state is invalid")
        elif (
            raw["target_next_action"] == "approve_experiment_execution"
            and project.state.next_action
            in {"prepare_experiment_self_test", "register_experiment_self_test"}
            and SELF_TEST_REPORT_PATH not in project.state.artifacts
            and _state_sha256(
                replace(
                    project.state,
                    next_action="approve_experiment_execution",
                )
            )
            == raw["prior_state_sha256"]
        ):
            pass
        elif (
            project.state.next_action
            in {"prepare_experiment_self_test", "register_experiment_self_test"}
            and project.state.artifacts.get(SELF_TEST_REPORT_PATH) == artifact
            and _state_sha256(
                replace(
                    project.state,
                    next_action=raw["target_next_action"],
                )
            )
            == raw["target_state_sha256"]
        ):
            pass
        else:
            raise ValueError("pending self-test registration state changed")
        return _PendingSelfTestRegistration(
            project_id=raw["project_id"],
            artifact=artifact,
            event_log_size=raw["event_log_size"],
            event_log_prefix_sha256=raw["event_log_prefix_sha256"],
            prior_state_sha256=raw["prior_state_sha256"],
            target_state_sha256=raw["target_state_sha256"],
            target_next_action=raw["target_next_action"],
            event=event,
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise ValueError(
            "experiment_self_test_registration_recovery_invalid"
        ) from error


def _complete_self_test_event_log_identity(
    project: ResearchProject,
) -> tuple[int, str]:
    try:
        from .events import event_log_for

        for _event in event_log_for(project.root).iter_events():
            pass
        path = project.root / "evaluation/events.jsonl"
        if not path.exists():
            return 0, hashlib.sha256(b"").hexdigest()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError("event log must be a regular file")
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(descriptor, 64 * 1024):
                digest.update(chunk)
                size += len(chunk)
            return size, digest.hexdigest()
        finally:
            os.close(descriptor)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(
            "experiment_self_test_registration_recovery_invalid"
        ) from error


def _self_test_registration_event_tail(
    project: ResearchProject, pending: _PendingSelfTestRegistration
) -> bytes:
    from .events import MAX_EVENT_RECORD_BYTES

    path = project.root / "evaluation/events.jsonl"
    if not path.exists():
        if pending.event_log_size == 0:
            return b""
        raise ValueError("experiment_self_test_registration_recovery_invalid")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            file_stat = os.fstat(descriptor)
            total_size = file_stat.st_size
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or total_size < pending.event_log_size
                or total_size - pending.event_log_size > MAX_EVENT_RECORD_BYTES
            ):
                raise ValueError("experiment_self_test_registration_recovery_invalid")
            digest = hashlib.sha256()
            remaining = pending.event_log_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    raise ValueError(
                        "experiment_self_test_registration_recovery_invalid"
                    )
                digest.update(chunk)
                remaining -= len(chunk)
            if digest.hexdigest() != pending.event_log_prefix_sha256:
                raise ValueError("experiment_self_test_registration_recovery_invalid")
            tail = os.read(descriptor, MAX_EVENT_RECORD_BYTES + 1)
            if len(tail) > MAX_EVENT_RECORD_BYTES or os.read(descriptor, 1):
                raise ValueError("experiment_self_test_registration_recovery_invalid")
            return tail
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == (
            "experiment_self_test_registration_recovery_invalid"
        ):
            raise
        raise ValueError(
            "experiment_self_test_registration_recovery_invalid"
        ) from error


def _truncate_self_test_registration_event_tail(
    project: ResearchProject, offset: int
) -> None:
    path = project.root / "evaluation/events.jsonl"
    descriptor = os.open(
        path,
        os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.ftruncate(descriptor, offset)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _complete_pending_self_test_registration(
    project: ResearchProject,
    pending: _PendingSelfTestRegistration,
) -> ArtifactRef:
    from .events import EventLog, EvaluationEvent, event_log_for

    if not isinstance(pending.event, EvaluationEvent):
        raise ValueError("experiment_self_test_registration_recovery_invalid")
    record = EventLog._bounded_record(pending.event)
    tail = _self_test_registration_event_tail(project, pending)
    if tail != record:
        if tail:
            ownership_marker = pending.artifact.sha256.encode("ascii")
            if not record.startswith(tail) or ownership_marker not in tail:
                raise ValueError("experiment_self_test_registration_recovery_invalid")
            _truncate_self_test_registration_event_tail(project, pending.event_log_size)
        event_log_for(project.root).append_locked(
            pending.event,
            expected_offset=pending.event_log_size,
        )
    if _self_test_registration_event_tail(project, pending) != record:
        raise OSError("self-test registration event was not persisted")

    current = ResearchProject.open_readonly(project.root)
    current_identity = _state_sha256(current.state)
    if current_identity == pending.prior_state_sha256:
        target_state = replace(
            current.state,
            next_action=pending.target_next_action,
            artifacts={
                **current.state.artifacts,
                SELF_TEST_REPORT_PATH: pending.artifact,
            },
        )
        if _state_sha256(target_state) != pending.target_state_sha256:
            raise ValueError("experiment_self_test_registration_recovery_invalid")
        current = current.persist_state(target_state)
    elif (
        pending.target_next_action == "approve_experiment_execution"
        and current.state.next_action
        in {"prepare_experiment_self_test", "register_experiment_self_test"}
        and SELF_TEST_REPORT_PATH not in current.state.artifacts
        and _state_sha256(
            replace(
                current.state,
                next_action="approve_experiment_execution",
            )
        )
        == pending.prior_state_sha256
    ):
        target_state = replace(
            current.state,
            next_action=pending.target_next_action,
            artifacts={
                **current.state.artifacts,
                SELF_TEST_REPORT_PATH: pending.artifact,
            },
        )
        if _state_sha256(target_state) != pending.target_state_sha256:
            raise ValueError("experiment_self_test_registration_recovery_invalid")
        current = current.persist_state(target_state)
    elif (
        current.state.next_action
        in {"prepare_experiment_self_test", "register_experiment_self_test"}
        and current.state.artifacts.get(SELF_TEST_REPORT_PATH) == pending.artifact
        and _state_sha256(
            replace(
                current.state,
                next_action=pending.target_next_action,
            )
        )
        == pending.target_state_sha256
    ):
        current = current.persist_state(
            replace(
                current.state,
                next_action=pending.target_next_action,
            )
        )
    elif current_identity != pending.target_state_sha256:
        raise ValueError("experiment_self_test_registration_recovery_invalid")
    if (
        current.state.artifacts.get(SELF_TEST_REPORT_PATH) != pending.artifact
        or current.state.next_action != pending.target_next_action
    ):
        raise ValueError("experiment_self_test_registration_recovery_invalid")
    _clear_self_test_registration_pending(current)
    return pending.artifact


def _current_registered_self_test(
    project: ResearchProject, *, environment: ExecutionEnvironment | None = None
) -> ArtifactRef:
    try:
        if os.path.lexists(_self_test_registration_pending_path(project)):
            raise ValueError("self-test registration is incomplete")
        package = validate_experiment_package_contract(project)
        artifact = validate_registered_self_test(
            project, package, environment=environment
        )
        registered = project.state.artifacts.get(SELF_TEST_REPORT_PATH)
        if registered != artifact:
            raise ValueError("self-test report is not registered")
        if not _self_test_registration_event_is_grounded(project, artifact):
            raise ValueError("self-test registration event is missing")
        return artifact
    except (OSError, ValueError) as error:
        if str(error) == "execution_environment_unavailable":
            raise ValueError("execution_environment_unavailable") from error
        if str(error) == "self_test environment fingerprint does not match":
            raise ValueError("execution_environment_changed") from error
        raise ValueError("experiment_self_test_required") from error


def _self_test_registration_event_is_grounded(
    project: ResearchProject, artifact: ArtifactRef
) -> bool:
    """Return whether one bounded event exactly grounds the current report."""
    from .events import event_log_for

    expected_payload = {
        "path": artifact.path,
        "sha256": artifact.sha256,
        "size": artifact.size,
    }
    for event in event_log_for(project.root).iter_events():
        if (
            event.type == "experiment_self_test_registered"
            and event.project_id == project.state.project_id
            and isinstance(event.payload.get("size"), int)
            and not isinstance(event.payload.get("size"), bool)
            and event.payload == expected_payload
        ):
            return True
    return False


def prepare_experiment_self_test(
    project: ResearchProject,
) -> SelfTestPreparationStatus:
    """Return a verified complete argv without executing or approving the package."""
    current = ResearchProject.open_readonly(project.root)
    state = current.state
    if (
        state.current_stage != 12
        or 11 not in state.completed_stages
        or state.status.value != "awaiting_approval"
        or state.next_action
        not in {
            "prepare_experiment_self_test",
            "register_experiment_self_test",
            "approve_experiment_execution",
        }
    ):
        raise ValueError("experiment_self_test_preparation_unavailable")
    if os.path.lexists(current.root / SELF_TEST_REPORT_PATH):
        raise ValueError("experiment_self_test_report_exists")
    try:
        package = validate_experiment_package_contract(current)
    except (OSError, ValueError) as error:
        raise ValueError("experiment_package_invalid") from error
    try:
        environment = inspect_execution_environment(
            Path(sys.executable).resolve(strict=True),
            package.required_distributions,
        )
    except (OSError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    try:
        if validate_experiment_package_contract(current) != package:
            raise ValueError("experiment_package_invalid")
    except (OSError, ValueError) as error:
        raise ValueError("experiment_package_invalid") from error
    return SelfTestPreparationStatus(
        argv=(environment.launcher, package.entry_point, *package.self_test_argv),
        environment_fingerprint=environment.fingerprint,
        package_contract_sha256=package.contract_sha256,
        report_path=SELF_TEST_REPORT_PATH,
        registration_argv=(
            "researchclaw-codex",
            "experiment",
            "register-self-test",
            str(current.root.resolve()),
            "--report",
            SELF_TEST_REPORT_PATH,
            "--confirm-self-test",
            "--json",
        ),
    )


@project_mutation
def register_experiment_self_test(
    project: ResearchProject, report_path: str
) -> ArtifactRef:
    """Register one externally produced, current known-answer self-test report."""
    current = ResearchProject.open(project.root)
    state = current.state
    if (
        state.current_stage != 12
        or 11 not in state.completed_stages
        or state.status.value != "awaiting_approval"
        or state.next_action
        not in {
            "prepare_experiment_self_test",
            "register_experiment_self_test",
            "approve_experiment_execution",
            "report_missing_execution_inputs",
        }
    ):
        raise ValueError("experiment_self_test_registration_unavailable")
    if report_path != SELF_TEST_REPORT_PATH:
        raise ValueError("experiment_self_test_required")
    try:
        package = validate_experiment_package_contract(current)
        artifact = validate_registered_self_test(current, package)
    except (OSError, ValueError) as error:
        raise ValueError("experiment_self_test_required") from error

    pending = _load_self_test_registration_pending(current)
    if pending is not None:
        if pending.artifact != artifact:
            raise ValueError("experiment_self_test_registration_recovery_invalid")
        completed = _complete_pending_self_test_registration(current, pending)
        _current_registered_self_test(ResearchProject.open_readonly(current.root))
        return completed

    try:
        already_grounded = _self_test_registration_event_is_grounded(current, artifact)
    except (OSError, ValueError) as error:
        raise ValueError(
            "experiment_self_test_registration_recovery_invalid"
        ) from error
    if (
        already_grounded
        and current.state.artifacts.get(SELF_TEST_REPORT_PATH) == artifact
    ):
        return artifact

    from .events import EvaluationEvent

    target_next_action = (
        "approve_experiment_execution"
        if state.next_action
        in {
            "prepare_experiment_self_test",
            "register_experiment_self_test",
            "approve_experiment_execution",
        }
        else state.next_action
    )
    target_state = replace(
        state,
        next_action=target_next_action,
        artifacts={**state.artifacts, SELF_TEST_REPORT_PATH: artifact},
    )
    event_log_size, event_log_prefix_sha256 = _complete_self_test_event_log_identity(
        current
    )
    event = EvaluationEvent.create(
        "experiment_self_test_registered",
        state.project_id,
        {
            "path": artifact.path,
            "sha256": artifact.sha256,
            "size": artifact.size,
        },
    )
    pending = _PendingSelfTestRegistration(
        project_id=state.project_id,
        artifact=artifact,
        event_log_size=event_log_size,
        event_log_prefix_sha256=event_log_prefix_sha256,
        prior_state_sha256=_state_sha256(state),
        target_state_sha256=_state_sha256(target_state),
        target_next_action=target_next_action,
        event=event,
    )
    _persist_self_test_registration_pending(current, pending)
    completed = _complete_pending_self_test_registration(current, pending)
    _current_registered_self_test(ResearchProject.open_readonly(current.root))
    return completed
