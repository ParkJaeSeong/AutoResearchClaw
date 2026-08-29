"""Pure structural validation for stage-10 computational packages."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from packaging.requirements import InvalidRequirement, Requirement

from .filesystem_baseline import FilesystemEntry, snapshot_project


MANIFEST_FIELDS = {
    "schema_version",
    "project_id",
    "design_sha256",
    "validation_type",
    "files",
    "entry_point",
    "config_path",
    "runtime",
    "input_contract",
    "output_contract",
    "commands",
    "prohibitions",
    "reproducibility",
}
FILE_FIELDS = {"path", "role", "sha256"}
CONFIG_FIELDS = {
    "schema_version",
    "project_id",
    "design_sha256",
    "datasets",
    "baselines",
    "split_strategy",
    "metrics",
    "seeds",
    "input_contract",
    "output_contract",
    "traceability",
}

MANIFEST_PATH = "experiment/package_manifest.json"
CODE_PATHS = (
    "experiment/code/README.md",
    "experiment/code/main.py",
    "experiment/code/config.json",
    "experiment/code/requirements.txt",
    "experiment/code/tests/test_smoke.py",
)
REQUIRED_OUTPUTS = (MANIFEST_PATH, *CODE_PATHS)
_PYTHON_PATHS = (
    "experiment/code/main.py",
    "experiment/code/tests/test_smoke.py",
)
_REQUIREMENTS_PATH = "experiment/code/requirements.txt"
_README_PATH = "experiment/code/README.md"
_EXPECTED_COMMANDS = {
    "dry_run": "python experiment/code/main.py --config experiment/code/config.json --dry-run",
    "smoke_test": "python -m pytest experiment/code/tests/test_smoke.py -q",
}
_TRACEABILITY_FIELDS = (
    "datasets",
    "baselines",
    "split_strategy",
    "metrics",
    "seeds",
    "input_contract",
    "output_contract",
)
_TRACEABILITY_SOURCES = {
    "datasets": frozenset({"method.datasets"}),
    "baselines": frozenset({"method.baselines", "comparators"}),
    "split_strategy": frozenset({"method.split_strategy"}),
    "metrics": frozenset({"metrics"}),
    "seeds": frozenset({"reproducibility", "reproducibility.protocol_version"}),
    "input_contract": frozenset({"evidence_sources", "method.datasets"}),
    "output_contract": frozenset({"metrics", "success_criteria", "failure_criteria"}),
}
_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "argparse",
        "json",
        "pathlib",
        "typing",
        "experiment.code.main",
    }
)
_ALLOWED_DISTRIBUTIONS = frozenset({"pytest"})
_ALLOWED_CONSTRUCTOR_CHAINS = frozenset(
    {
        "Path",
        "pathlib.Path",
        "PurePath",
        "pathlib.PurePath",
        "PurePosixPath",
        "pathlib.PurePosixPath",
        "PureWindowsPath",
        "pathlib.PureWindowsPath",
        "json.JSONDecoder",
        "json.JSONEncoder",
    }
)
_ALLOWED_BUILTIN_CALLS = frozenset(
    {
        "FileNotFoundError",
        "RuntimeError",
        "TypeError",
        "ValueError",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "getattr",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "open",
        "print",
        "range",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
)
_ALLOWED_OBJECT_METHODS = frozenset(
    {
        "add_argument",
        "append",
        "close",
        "decode",
        "encode",
        "get",
        "is_absolute",
        "is_dir",
        "is_file",
        "items",
        "keys",
        "open",
        "parse_args",
        "read",
        "read_bytes",
        "read_text",
        "sort",
        "startswith",
        "values",
        "write",
        "write_bytes",
        "write_text",
    }
)
_FAKE_RESULT_NAME = re.compile(
    r"(?:synthetic|fake|dummy)[_\s-]*(?:result|results|output|outputs|metric|metrics|prediction|predictions)",
    re.IGNORECASE,
)
_TRACEABILITY_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_PATH_ASSIGNMENT = re.compile(r"(?:^|_)(?:path|file|dir|directory|root)(?:$|_)", re.IGNORECASE)
_FILESYSTEM_CALLS = frozenset(
    {
        "Path",
        "PurePath",
        "PurePosixPath",
        "PureWindowsPath",
        "pathlib.Path",
        "pathlib.PurePath",
        "pathlib.PurePosixPath",
        "pathlib.PureWindowsPath",
        "open",
        "io.open",
        "os.open",
        "os.access",
        "os.chdir",
        "os.chmod",
        "os.listdir",
        "os.lstat",
        "os.makedirs",
        "os.mkdir",
        "os.path.abspath",
        "os.path.join",
        "os.path.realpath",
        "os.readlink",
        "os.remove",
        "os.rename",
        "os.replace",
        "os.rmdir",
        "os.scandir",
        "os.stat",
        "os.symlink",
        "os.unlink",
        "os.walk",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
        "glob.glob",
        "glob.iglob",
    }
)
_INPUT_CONTRACT_FIELDS = {"design_binding", "required_paths", "required_fields"}
_OUTPUT_CONTRACT_FIELDS = {"design_binding", "result_path", "required_fields"}
_SPLIT_STRATEGY_FIELDS = {
    "design_binding",
    "groups",
    "isolation_key",
    "overlap_policy",
}
_SEEDS_FIELDS = {"design_binding", "values"}
_RUNTIME_FIELDS = {"python"}
_PROHIBITION_FIELDS = {
    "stage_10_execution",
    "network_access",
    "external_llm_calls",
    "nested_agent_processes",
}
_REPRODUCIBILITY_FIELDS = {"design_sha256", "seeds", "dependencies"}
_SPLIT_GROUPS = {"train", "validation", "calibration", "test"}
_LATER_RESULT_PATH = "experiment/results.json"


@dataclass(frozen=True)
class ComputationalPackageIssue:
    code: str
    path: str
    message: str


def _issue(
    issues: list[ComputationalPackageIssue], code: str, path: str, message: str
) -> None:
    issues.append(ComputationalPackageIssue(code, path, message))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_object(
    text: object,
    path: str,
    issues: list[ComputationalPackageIssue],
) -> dict[str, Any] | None:
    if not isinstance(text, str):
        _issue(issues, "missing_artifact", path, "required artifact is missing")
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        _issue(issues, "invalid_format", path, "artifact must be valid JSON")
        return None
    if not isinstance(value, dict):
        _issue(issues, "invalid_format", path, "artifact must contain a JSON object")
        return None
    return value


def _validate_closed_fields(
    value: dict[str, Any],
    fields: set[str],
    path: str,
    label: str,
    issues: list[ComputationalPackageIssue],
) -> bool:
    valid = True
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        _issue(
            issues,
            "unknown_field",
            path,
            f"{label} has undeclared fields: {', '.join(unknown)}",
        )
        valid = False
    if missing:
        _issue(
            issues,
            "missing_required_field",
            path,
            f"{label} requires fields: {', '.join(missing)}",
        )
        valid = False
    return valid


def _is_schema_version(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


def _validate_manifest_files(
    manifest: dict[str, Any], issues: list[ComputationalPackageIssue]
) -> dict[str, str]:
    declared_hashes: dict[str, str] = {}
    files = manifest.get("files")
    if not isinstance(files, list):
        _issue(issues, "invalid_format", MANIFEST_PATH, "files must be a JSON list")
        return declared_hashes

    for index, value in enumerate(files, start=1):
        if not isinstance(value, dict):
            _issue(
                issues,
                "invalid_format",
                MANIFEST_PATH,
                f"files[{index}] must be a JSON object",
            )
            continue
        if not _validate_closed_fields(
            value, FILE_FIELDS, MANIFEST_PATH, f"files[{index}]", issues
        ):
            continue
        path = value["path"]
        role = value["role"]
        sha256 = value["sha256"]
        if not isinstance(path, str) or not path:
            _issue(issues, "invalid_format", MANIFEST_PATH, f"files[{index}].path must be text")
            continue
        if not isinstance(role, str) or not role.strip():
            _issue(issues, "invalid_format", MANIFEST_PATH, f"files[{index}].role must be text")
        if not isinstance(sha256, str) or len(sha256) != 64:
            _issue(issues, "invalid_format", MANIFEST_PATH, f"files[{index}].sha256 must be SHA-256")
            continue
        if path in declared_hashes:
            _issue(issues, "manifest_file_set", MANIFEST_PATH, f"files lists {path} more than once")
            continue
        declared_hashes[path] = sha256

    if set(declared_hashes) != set(CODE_PATHS):
        _issue(
            issues,
            "manifest_file_set",
            MANIFEST_PATH,
            "files must list exactly the five declared experiment/code artifacts",
        )
    return declared_hashes


def _validate_hashes(
    root: Path,
    declared_hashes: Mapping[str, str],
    issues: list[ComputationalPackageIssue],
) -> None:
    for relative_path in CODE_PATHS:
        path = root / relative_path
        if not path.is_file():
            _issue(issues, "missing_artifact", relative_path, "required artifact is missing")
            continue
        expected = declared_hashes.get(relative_path)
        if expected is not None and _sha256(path) != expected:
            _issue(
                issues,
                "hash_mismatch",
                relative_path,
                "artifact SHA-256 does not match package manifest",
            )


def _validate_on_disk_tree(
    root: Path,
    prepared_snapshot: tuple[FilesystemEntry, ...] | None,
    authorized_paths: frozenset[str],
    issues: list[ComputationalPackageIssue],
) -> None:
    if prepared_snapshot is None:
        _issue(
            issues,
            "missing_prepare_baseline",
            MANIFEST_PATH,
            "stage 10 must be prepared before its outputs are authored",
        )
        return
    baseline = {entry.path: entry for entry in prepared_snapshot}
    current = {entry.path: entry for entry in snapshot_project(root)}
    expected_outputs = set(REQUIRED_OUTPUTS)
    allowed_directories = {
        parent.as_posix()
        for output in REQUIRED_OUTPUTS
        for parent in Path(output).parents
        if parent.as_posix() != "."
    }
    added = set(current) - set(baseline)
    for relative in sorted(added - expected_outputs - allowed_directories):
        _issue(
            issues,
            "undeclared_artifact",
            relative,
            "filesystem paths added after Stage 10 prepare must be declared outputs",
        )
    for relative in sorted(set(baseline) - set(current)):
        _issue(
            issues,
            "undeclared_artifact",
            relative,
            "filesystem paths present at Stage 10 prepare must not be removed",
        )
    for relative in sorted(set(baseline) & set(current)):
        if relative in authorized_paths or baseline[relative] == current[relative]:
            continue
        _issue(
            issues,
            "modified_baseline_artifact",
            relative,
            "filesystem entries present at Stage 10 prepare must retain type and content",
        )
    for relative in sorted(expected_outputs - added):
        _issue(
            issues,
            "missing_output_delta",
            relative,
            "each declared Stage 10 output must be authored after its first prepare",
        )


def _validate_python_syntax(
    outputs: Mapping[str, str], issues: list[ComputationalPackageIssue]
) -> None:
    for path in _PYTHON_PATHS:
        source = outputs.get(path)
        if not isinstance(source, str):
            continue
        try:
            ast.parse(source, filename=path)
        except SyntaxError as error:
            _issue(issues, "invalid_python", path, f"Python syntax error: {error.msg}")


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent is not None else None
    return None


def _allowed_import(name: str) -> bool:
    return any(name == allowed or name.startswith(f"{allowed}.") for allowed in _ALLOWED_IMPORTS)


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _allowed_distribution(name: str) -> bool:
    return _normalized_distribution_name(name) in _ALLOWED_DISTRIBUTIONS


def _absolute_literal(value: object) -> bool:
    return (
        isinstance(value, str)
        and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute())
    )


def _constant_absolute_path(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and _absolute_literal(node.value)


def _assignment_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(name for element in node.elts for name in _assignment_names(element))
    return ()


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                aliases[imported.asname or imported.name.split(".")[0]] = imported.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for imported in node.names:
                aliases[imported.asname or imported.name] = f"{node.module}.{imported.name}"
    return aliases


def _subscript_key(node: ast.Subscript) -> object:
    return node.slice.value if isinstance(node.slice, ast.Constant) else None


def _resolved_call_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolved_call_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent is not None else None
    if isinstance(node, ast.Call):
        called = _resolved_call_name(node.func, aliases)
        if called in {"getattr", "builtins.getattr"} and len(node.args) >= 2:
            target = _resolved_call_name(node.args[0], aliases)
            attribute = (
                node.args[1].value
                if isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                else None
            )
            if target is not None and attribute is not None:
                return f"{target}.{attribute}"
            return None
        return f"{called}()" if called is not None else None
    if isinstance(node, ast.Subscript):
        parent = _resolved_call_name(node.value, aliases)
        key = _subscript_key(node)
        if parent == "sys.modules" and isinstance(key, str):
            return key
        if parent is not None and parent.endswith(".__dict__") and isinstance(key, str):
            return f"{parent.removesuffix('.__dict__')}.{key}"
        if parent in {"globals()", "locals()"} and isinstance(key, str):
            return key
        return None
    return None


def _forbidden_call(name: str | None) -> bool:
    if name is None:
        return False
    if name in {
        "eval",
        "exec",
        "builtins.eval",
        "builtins.exec",
        "__builtins__.eval",
        "__builtins__.exec",
        "__import__",
        "builtins.__import__",
        "__builtins__.__import__",
        "importlib.import_module",
        "pty.spawn",
    }:
        return True
    if name.startswith(("subprocess.", "multiprocessing.")):
        return True
    if name.startswith("asyncio.create_subprocess_"):
        return True
    if name.startswith("os."):
        operation = name.rsplit(".", maxsplit=1)[-1]
        return operation in {"system", "popen", "fork", "forkpty", "startfile"} or operation.startswith(
            ("spawn", "exec", "posix_spawn")
        )
    return False


def _call_is_dynamic_dispatch(node: ast.Call, aliases: Mapping[str, str]) -> bool:
    current = node.func
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Subscript):
        return _resolved_call_name(node.func, aliases) is None
    if not isinstance(current, ast.Call):
        return False
    root = _resolved_call_name(current.func, aliases)
    return root not in _ALLOWED_CONSTRUCTOR_CHAINS


def _call_has_allowed_provenance(
    node: ast.Call,
    aliases: Mapping[str, str],
    local_callables: frozenset[str],
) -> bool:
    name = _resolved_call_name(node.func, aliases)
    if name is None:
        return False
    if name in local_callables or name in _ALLOWED_BUILTIN_CALLS:
        return True
    if any(name == allowed or name.startswith(f"{allowed}.") for allowed in _ALLOWED_IMPORTS):
        return True
    if isinstance(node.func, ast.Attribute) and node.func.attr in _ALLOWED_OBJECT_METHODS:
        return True
    return False


def _call_writes_artifact(node: ast.Call, aliases: Mapping[str, str]) -> bool:
    name = _resolved_call_name(node.func, aliases)
    leaf = node.func.attr if isinstance(node.func, ast.Attribute) else None
    operation = name.rsplit(".", maxsplit=1)[-1] if name is not None else leaf
    if operation in {
        "write",
        "writelines",
        "write_text",
        "write_bytes",
        "touch",
        "replace",
        "rename",
        "unlink",
        "dump",
        "save",
        "savefig",
        "to_csv",
        "to_json",
        "to_parquet",
        "to_pickle",
    }:
        return True
    if operation in {"mkdir", "makedirs"}:
        return True
    if name is None:
        return False
    if name in {"os.open"} or name.startswith("shutil.copy") or name == "shutil.move":
        return True
    if operation == "open":
        mode: object = "r"
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = keyword.value.value
        mode_index = 1 if name in {"open", "io.open", "builtins.open"} else 0
        if len(node.args) > mode_index and isinstance(node.args[mode_index], ast.Constant):
            mode = node.args[mode_index].value
        return isinstance(mode, str) and any(marker in mode for marker in "wax+")
    return False


_UNKNOWN = object()


def _constant_value(
    node: ast.AST,
    *,
    constants: Mapping[str, object],
    dry_run: bool | None,
) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, _UNKNOWN)
    dotted = _dotted_name(node)
    if dotted is not None and dry_run is not None and re.search(
        r"(?:^|\.)dry_?run$", dotted, re.IGNORECASE
    ):
        return dry_run
    if isinstance(node, ast.UnaryOp):
        operand = _constant_value(node.operand, constants=constants, dry_run=dry_run)
        if operand is _UNKNOWN:
            return _UNKNOWN
        try:
            if isinstance(node.op, ast.Not):
                return not bool(operand)
            if isinstance(node.op, ast.UAdd):
                return +operand  # type: ignore[operator]
            if isinstance(node.op, ast.USub):
                return -operand  # type: ignore[operator]
            if isinstance(node.op, ast.Invert):
                return ~operand  # type: ignore[operator]
        except (TypeError, ValueError):
            return _UNKNOWN
    if isinstance(node, ast.BoolOp):
        values = [
            _constant_value(value, constants=constants, dry_run=dry_run)
            for value in node.values
        ]
        if isinstance(node.op, ast.And):
            if any(value is not _UNKNOWN and not bool(value) for value in values):
                return False
            return True if all(value is not _UNKNOWN for value in values) else _UNKNOWN
        if any(value is not _UNKNOWN and bool(value) for value in values):
            return True
        return False if all(value is not _UNKNOWN for value in values) else _UNKNOWN
    if isinstance(node, ast.Compare):
        left = _constant_value(node.left, constants=constants, dry_run=dry_run)
        comparators = [
            _constant_value(value, constants=constants, dry_run=dry_run)
            for value in node.comparators
        ]
        if left is _UNKNOWN or any(value is _UNKNOWN for value in comparators):
            return _UNKNOWN
        operations = {
            ast.Eq: lambda first, second: first == second,
            ast.NotEq: lambda first, second: first != second,
            ast.Lt: lambda first, second: first < second,
            ast.LtE: lambda first, second: first <= second,
            ast.Gt: lambda first, second: first > second,
            ast.GtE: lambda first, second: first >= second,
            ast.Is: lambda first, second: first is second,
            ast.IsNot: lambda first, second: first is not second,
            ast.In: lambda first, second: first in second,
            ast.NotIn: lambda first, second: first not in second,
        }
        try:
            values = [left, *comparators]
            return all(
                operations[type(operation)](values[index], values[index + 1])
                for index, operation in enumerate(node.ops)
                if type(operation) in operations
            ) and all(type(operation) in operations for operation in node.ops)
        except (TypeError, ValueError):
            return _UNKNOWN
    return _UNKNOWN


class _FlatNodeCollector(ast.NodeVisitor):
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


def _flat_nodes(node: ast.AST) -> list[ast.AST]:
    collector = _FlatNodeCollector()
    collector.visit(node)
    return collector.nodes


def _reachable_block(
    statements: list[ast.stmt],
    *,
    constants: Mapping[str, object],
    dry_run: bool | None,
) -> tuple[list[ast.AST], bool]:
    nodes: list[ast.AST] = []
    falls_through = True
    for statement in statements:
        if not falls_through:
            break
        statement_nodes, falls_through = _reachable_statement(
            statement, constants=constants, dry_run=dry_run
        )
        nodes.extend(statement_nodes)
    return nodes, falls_through


def _reachable_statement(
    statement: ast.stmt,
    *,
    constants: Mapping[str, object],
    dry_run: bool | None,
) -> tuple[list[ast.AST], bool]:
    if isinstance(statement, ast.If):
        nodes = [statement, *_flat_nodes(statement.test)]
        condition = _constant_value(
            statement.test, constants=constants, dry_run=dry_run
        )
        if condition is not _UNKNOWN:
            branch = statement.body if bool(condition) else statement.orelse
            branch_nodes, falls_through = _reachable_block(
                branch, constants=constants, dry_run=dry_run
            )
            return [*nodes, *branch_nodes], falls_through
        body_nodes, body_falls = _reachable_block(
            statement.body, constants=constants, dry_run=dry_run
        )
        else_nodes, else_falls = _reachable_block(
            statement.orelse, constants=constants, dry_run=dry_run
        )
        return [*nodes, *body_nodes, *else_nodes], body_falls or else_falls
    if isinstance(statement, ast.While):
        nodes = [statement, *_flat_nodes(statement.test)]
        condition = _constant_value(
            statement.test, constants=constants, dry_run=dry_run
        )
        if condition is not _UNKNOWN and not bool(condition):
            else_nodes, else_falls = _reachable_block(
                statement.orelse, constants=constants, dry_run=dry_run
            )
            return [*nodes, *else_nodes], else_falls
        body_nodes, _ = _reachable_block(
            statement.body, constants=constants, dry_run=dry_run
        )
        else_nodes, _ = _reachable_block(
            statement.orelse, constants=constants, dry_run=dry_run
        )
        return [*nodes, *body_nodes, *else_nodes], True
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        header_nodes = [statement]
        for item in statement.items:
            header_nodes.extend(_flat_nodes(item.context_expr))
            if item.optional_vars is not None:
                header_nodes.extend(_flat_nodes(item.optional_vars))
        body_nodes, falls_through = _reachable_block(
            statement.body, constants=constants, dry_run=dry_run
        )
        return [*header_nodes, *body_nodes], falls_through
    if isinstance(statement, ast.Try):
        body_nodes, body_falls = _reachable_block(
            statement.body, constants=constants, dry_run=dry_run
        )
        branch_nodes = list(body_nodes)
        branch_falls = body_falls
        for handler in statement.handlers:
            handler_nodes, handler_falls = _reachable_block(
                handler.body, constants=constants, dry_run=dry_run
            )
            branch_nodes.extend(handler_nodes)
            branch_falls = branch_falls or handler_falls
        else_nodes, else_falls = _reachable_block(
            statement.orelse, constants=constants, dry_run=dry_run
        )
        final_nodes, final_falls = _reachable_block(
            statement.finalbody, constants=constants, dry_run=dry_run
        )
        return (
            [statement, *branch_nodes, *else_nodes, *final_nodes],
            branch_falls and else_falls and final_falls,
        )
    if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
        return _flat_nodes(statement), False
    return _flat_nodes(statement), True


def _reachable_nodes(
    node: ast.AST,
    *,
    constants: Mapping[str, object] | None = None,
    dry_run: bool | None = None,
) -> list[ast.AST]:
    known = constants or {}
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
        nodes, _ = _reachable_block(node.body, constants=known, dry_run=dry_run)
        return nodes
    if isinstance(node, ast.Lambda):
        return _flat_nodes(node.body)
    return _flat_nodes(node)


def _top_level_functions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _local_callables(
    tree: ast.AST,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda]:
    callables: dict[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            callables[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and isinstance(
            node.value, ast.Lambda
        ):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                for name in _assignment_names(target):
                    callables[name] = node.value
    return callables


def _module_callable_names(tree: ast.Module) -> frozenset[str]:
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and isinstance(
            node.value, ast.Lambda
        ):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            names.update(
                name for target in targets for name in _assignment_names(target)
            )
    return frozenset(names)


def _expand_local_call_graph(
    initial_nodes: list[ast.AST],
    functions: Mapping[
        str, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    ],
    aliases: Mapping[str, str],
    *,
    dry_run: bool | None = None,
    available_callables: frozenset[str],
) -> list[ast.AST]:
    expanded = list(initial_nodes)
    available = set(available_callables)
    available.update(
        name
        for name, callable_node in functions.items()
        if callable_node in initial_nodes
    )
    queued = [
        name.rsplit(".", maxsplit=1)[-1]
        for node in initial_nodes
        if isinstance(node, ast.Call)
        and (name := _resolved_call_name(node.func, aliases)) is not None
    ]
    visited: set[str] = set()
    while queued:
        function_name = queued.pop()
        if (
            function_name in visited
            or function_name not in functions
            or function_name not in available
        ):
            continue
        visited.add(function_name)
        nodes = _reachable_nodes(functions[function_name], dry_run=dry_run)
        expanded.extend(nodes)
        available.update(
            name
            for name, callable_node in functions.items()
            if callable_node in nodes
        )
        queued.extend(
            name.rsplit(".", maxsplit=1)[-1]
            for node in nodes
            if isinstance(node, ast.Call)
            and (name := _resolved_call_name(node.func, aliases)) is not None
        )
    return expanded


def _nodes_write_artifacts(
    nodes: list[ast.AST], aliases: Mapping[str, str]
) -> bool:
    return any(
        isinstance(node, ast.Call) and _call_writes_artifact(node, aliases)
        for node in nodes
    )


def _smoke_reaches_artifact_write(
    tree: ast.Module, aliases: Mapping[str, str]
) -> bool:
    functions = _top_level_functions(tree)
    callables = _local_callables(tree)
    module_callables = _module_callable_names(tree)
    for name, function in functions.items():
        if not name.startswith("test_"):
            continue
        nodes = _expand_local_call_graph(
            _reachable_nodes(function),
            callables,
            aliases,
            available_callables=module_callables,
        )
        if _nodes_write_artifacts(nodes, aliases):
            return True
    return False


def _dry_run_reaches_artifact_write(
    tree: ast.Module, aliases: Mapping[str, str]
) -> bool:
    functions = _top_level_functions(tree)
    callables = _local_callables(tree)
    module_callables = _module_callable_names(tree)
    main = functions.get("main")
    if main is None:
        return False
    main_nodes = _expand_local_call_graph(
        _reachable_nodes(main, dry_run=True),
        callables,
        aliases,
        dry_run=True,
        available_callables=module_callables,
    )
    return _nodes_write_artifacts(main_nodes, aliases)


def _module_import_reaches_artifact_write(
    tree: ast.Module, aliases: Mapping[str, str]
) -> bool:
    callables = _local_callables(tree)
    nodes = _expand_local_call_graph(
        _reachable_nodes(tree, constants={"__name__": "__imported__"}),
        callables,
        aliases,
        available_callables=_module_callable_names(tree),
    )
    return _nodes_write_artifacts(nodes, aliases)


def _call_uses_absolute_path(node: ast.Call, aliases: Mapping[str, str]) -> bool:
    name = _resolved_call_name(node.func, aliases)
    if name not in _FILESYSTEM_CALLS:
        return False
    return any(_constant_absolute_path(argument) for argument in node.args) or any(
        keyword.arg in {"path", "file", "filename", "src", "dst"}
        and _constant_absolute_path(keyword.value)
        for keyword in node.keywords
    )


def _assignment_uses_absolute_path(node: ast.AST) -> bool:
    if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        return False
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    value = node.value
    return _constant_absolute_path(value) and any(
        _PATH_ASSIGNMENT.search(name) is not None
        for target in targets
        for name in _assignment_names(target)
    )


def _add_callable_aliases(tree: ast.AST, aliases: dict[str, str]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        resolved = _resolved_call_name(node.value, aliases)
        if resolved is None:
            continue
        for target in targets:
            for name in _assignment_names(target):
                aliases[name] = resolved or name


def _validate_python_capabilities(
    outputs: Mapping[str, str], issues: list[ComputationalPackageIssue]
) -> None:
    for path in _PYTHON_PATHS:
        source = outputs.get(path)
        if not isinstance(source, str):
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            continue

        aliases = _import_aliases(tree)
        _add_callable_aliases(tree, aliases)
        local_callables = frozenset(_local_callables(tree))
        forbidden = False
        unsafe_path = False
        fake_result_assignment = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                forbidden = forbidden or any(not _allowed_import(alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                forbidden = forbidden or (
                    node.module is None
                    or node.level != 0
                    or (
                        not _allowed_import(node.module)
                        or any(
                            not _allowed_import(f"{node.module}.{alias.name}")
                            for alias in node.names
                        )
                    )
                )
            elif isinstance(node, ast.Call):
                forbidden = forbidden or _forbidden_call(
                    _resolved_call_name(node.func, aliases)
                ) or _call_is_dynamic_dispatch(node, aliases) or not _call_has_allowed_provenance(
                    node, aliases, local_callables
                )
                unsafe_path = unsafe_path or _call_uses_absolute_path(node, aliases)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                fake_result_assignment = fake_result_assignment or any(
                    _FAKE_RESULT_NAME.search(name) is not None
                    for target in targets
                    for name in _assignment_names(target)
                )
                unsafe_path = unsafe_path or _assignment_uses_absolute_path(node)

        if fake_result_assignment and not (
            path == "experiment/code/tests/test_smoke.py"
            and not _smoke_reaches_artifact_write(tree, aliases)
        ):
            forbidden = True
        if path == "experiment/code/tests/test_smoke.py" and _smoke_reaches_artifact_write(
            tree, aliases
        ):
            forbidden = True
        if path == "experiment/code/main.py" and _dry_run_reaches_artifact_write(
            tree, aliases
        ):
            forbidden = True
        if _module_import_reaches_artifact_write(tree, aliases):
            forbidden = True
        if forbidden:
            _issue(
                issues,
                "forbidden_capability",
                path,
                "generated Python uses a prohibited capability or synthetic-result fallback",
            )
        if unsafe_path:
            _issue(issues, "unsafe_path", path, "generated Python contains an absolute literal path")


def _validate_requirements(
    requirements: object, issues: list[ComputationalPackageIssue]
) -> None:
    if not isinstance(requirements, str):
        return
    for line_number, raw_line in enumerate(requirements.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if (
            stripped.startswith("-")
            or " @ " in stripped
            or "://" in stripped
            or lowered.startswith(("git+", "hg+", "svn+", "bzr+"))
        ):
            _issue(
                issues,
                "forbidden_dependency_source",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} must not use an option, URL, VCS source, or direct reference",
            )
            continue
        line = raw_line.split(" #", maxsplit=1)[0].strip()
        if not line:
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            _issue(
                issues,
                "invalid_dependency",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} must be a valid PEP 508 requirement",
            )
            continue
        if requirement.url is not None:
            _issue(
                issues,
                "forbidden_dependency_source",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} must not use a direct reference",
            )
            continue
        if not _allowed_distribution(requirement.name):
            _issue(
                issues,
                "forbidden_capability",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} declares a prohibited dependency",
            )
        specifiers = tuple(requirement.specifier)
        compatible = any(specifier.operator == "~=" for specifier in specifiers)
        exact = any(
            specifier.operator == "==" and "*" not in specifier.version
            for specifier in specifiers
        ) and all(specifier.operator in {"==", "!="} for specifier in specifiers)
        bounded_range = (
            any(specifier.operator in {">", ">="} for specifier in specifiers)
            and any(specifier.operator in {"<", "<="} for specifier in specifiers)
            and all(
                specifier.operator in {">", ">=", "<", "<=", "!="}
                for specifier in specifiers
            )
        )
        bounded = compatible or exact or bounded_range
        if not bounded:
            _issue(
                issues,
                "unbounded_dependency",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} must use a bounded version constraint",
            )


def _design_path_is_nonempty(design: object, path: object) -> bool:
    if not isinstance(path, str) or _TRACEABILITY_PATH.fullmatch(path) is None:
        return False
    value = design
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return False
        value = value[segment]
    return value not in (None, "", [], {})


def _config_section_is_nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return value is not None and not isinstance(value, bool)


def _design_path_value(design: object, path: object) -> object:
    if not isinstance(path, str) or _TRACEABILITY_PATH.fullmatch(path) is None:
        return None
    value = design
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_text_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        _nonempty_text(item) for item in value
    )


def _integer_seed_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(seed, int) and not isinstance(seed, bool) for seed in value
    )


def _project_relative_path(value: object) -> bool:
    if not _nonempty_text(value):
        return False
    path = Path(value)
    windows_path = PureWindowsPath(value)
    return (
        not path.is_absolute()
        and not windows_path.is_absolute()
        and ".." not in path.parts
        and ".." not in windows_path.parts
    )


def _closed_contract(value: object, fields: set[str]) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and set(value) == fields else None


def _validate_config_contract(
    design: object,
    config: dict[str, Any],
    issues: list[ComputationalPackageIssue],
) -> None:
    path = "experiment/code/config.json"
    traceability = config.get("traceability")
    if not isinstance(design, dict) or not isinstance(traceability, dict):
        return

    mismatch = False
    for field in ("datasets", "baselines", "metrics"):
        source = _design_path_value(design, traceability.get(field))
        mismatch = mismatch or config.get(field) != source
    if mismatch:
        _issue(
            issues,
            "config_design_mismatch",
            path,
            "datasets, baselines, and metrics must exactly preserve their approved design values",
        )

    invalid = False
    split = _closed_contract(config.get("split_strategy"), _SPLIT_STRATEGY_FIELDS)
    split_source = _design_path_value(design, traceability.get("split_strategy"))
    invalid = invalid or split is None
    if split is not None:
        groups = split.get("groups")
        invalid = invalid or (
            not isinstance(split_source, dict)
            or set(split_source) != {"description", "isolation_key"}
            or split.get("design_binding") != split_source
            or not isinstance(groups, list)
            or len(groups) != len(_SPLIT_GROUPS)
            or set(groups) != _SPLIT_GROUPS
            or split.get("isolation_key") != split_source.get("isolation_key")
            or split.get("overlap_policy") != "disjoint"
        )

    seeds = _closed_contract(config.get("seeds"), _SEEDS_FIELDS)
    seed_source = _design_path_value(design, traceability.get("seeds"))
    invalid = invalid or seeds is None
    if seeds is not None:
        invalid = invalid or (
            seeds.get("design_binding") != seed_source
            or not _integer_seed_list(seeds.get("values"))
        )

    input_contract = _closed_contract(
        config.get("input_contract"), _INPUT_CONTRACT_FIELDS
    )
    input_source = _design_path_value(design, traceability.get("input_contract"))
    invalid = invalid or input_contract is None
    if input_contract is not None:
        required_paths = input_contract.get("required_paths")
        invalid = invalid or (
            input_contract.get("design_binding") != input_source
            or not isinstance(required_paths, list)
            or not required_paths
            or not all(_project_relative_path(item) for item in required_paths)
            or not _nonempty_text_list(input_contract.get("required_fields"))
        )

    output_contract = _closed_contract(
        config.get("output_contract"), _OUTPUT_CONTRACT_FIELDS
    )
    output_source = _design_path_value(design, traceability.get("output_contract"))
    invalid = invalid or output_contract is None
    if output_contract is not None:
        invalid = invalid or (
            output_contract.get("design_binding") != output_source
            or output_contract.get("result_path") != _LATER_RESULT_PATH
            or not _nonempty_text_list(output_contract.get("required_fields"))
        )

    if invalid:
        _issue(
            issues,
            "invalid_config_contract",
            path,
            "split, seed, input, and output contracts must be typed, design-bound, non-empty, and use isolated groups",
        )


def _validate_manifest_contracts(
    manifest: dict[str, Any],
    config: dict[str, Any] | None,
    design_sha256: str,
    issues: list[ComputationalPackageIssue],
) -> None:
    runtime = _closed_contract(manifest.get("runtime"), _RUNTIME_FIELDS)
    input_contract = _closed_contract(
        manifest.get("input_contract"), _INPUT_CONTRACT_FIELDS
    )
    output_contract = _closed_contract(
        manifest.get("output_contract"), _OUTPUT_CONTRACT_FIELDS
    )
    prohibitions = _closed_contract(
        manifest.get("prohibitions"), _PROHIBITION_FIELDS
    )
    reproducibility = _closed_contract(
        manifest.get("reproducibility"), _REPRODUCIBILITY_FIELDS
    )
    valid = runtime is not None and _nonempty_text(runtime.get("python"))
    valid = valid and input_contract is not None and output_contract is not None
    if input_contract is not None:
        required_paths = input_contract.get("required_paths")
        valid = valid and (
            _config_section_is_nonempty(input_contract.get("design_binding"))
            and isinstance(required_paths, list)
            and bool(required_paths)
            and all(_project_relative_path(item) for item in required_paths)
            and _nonempty_text_list(input_contract.get("required_fields"))
        )
    if output_contract is not None:
        valid = valid and (
            _config_section_is_nonempty(output_contract.get("design_binding"))
            and output_contract.get("result_path") == _LATER_RESULT_PATH
            and _nonempty_text_list(output_contract.get("required_fields"))
        )
    valid = valid and prohibitions is not None
    if prohibitions is not None:
        valid = valid and (
            prohibitions.get("stage_10_execution") is False
            and prohibitions.get("network_access") is False
            and type(prohibitions.get("external_llm_calls")) is int
            and prohibitions.get("external_llm_calls") == 0
            and type(prohibitions.get("nested_agent_processes")) is int
            and prohibitions.get("nested_agent_processes") == 0
        )
    valid = valid and reproducibility is not None
    if reproducibility is not None:
        valid = valid and (
            reproducibility.get("design_sha256") == design_sha256
            and _integer_seed_list(reproducibility.get("seeds"))
            and reproducibility.get("dependencies") == "bounded"
        )
    if config is not None:
        valid = valid and (
            manifest.get("input_contract") == config.get("input_contract")
            and manifest.get("output_contract") == config.get("output_contract")
            and isinstance(reproducibility, dict)
            and isinstance(config.get("seeds"), dict)
            and reproducibility.get("seeds") == config["seeds"].get("values")
        )
    if not valid:
        _issue(
            issues,
            "invalid_manifest_contract",
            MANIFEST_PATH,
            "runtime, input/output contracts, prohibitions, and reproducibility must match their closed non-empty schemas",
        )


def _validate_traceability(
    design_json: str, config: dict[str, Any], issues: list[ComputationalPackageIssue]
) -> None:
    try:
        design = json.loads(design_json)
    except json.JSONDecodeError:
        design = None
    traceability = config.get("traceability")
    if not isinstance(traceability, dict) or set(traceability) != set(
        _TRACEABILITY_FIELDS
    ) or any(
        traceability.get(field) not in _TRACEABILITY_SOURCES[field]
        or not _design_path_is_nonempty(design, traceability.get(field))
        or not _config_section_is_nonempty(config.get(field))
        for field in _TRACEABILITY_FIELDS
    ):
        _issue(
            issues,
            "missing_traceability",
            "experiment/code/config.json",
            "traceability must map every required config section to a non-empty stage-9 field path",
        )


def _call_names(
    nodes: list[ast.AST], aliases: Mapping[str, str]
) -> set[str]:
    return {
        name
        for node in nodes
        if isinstance(node, ast.Call)
        and (name := _resolved_call_name(node.func, aliases)) is not None
    }


def _node_literals(nodes: list[ast.AST]) -> set[str]:
    return {
        node.value
        for node in nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _validate_python_contracts(
    outputs: Mapping[str, str], issues: list[ComputationalPackageIssue]
) -> None:
    main_path = "experiment/code/main.py"
    main_source = outputs.get(main_path)
    if isinstance(main_source, str):
        try:
            tree = ast.parse(main_source, filename=main_path)
        except SyntaxError:
            tree = None
        if tree is not None:
            aliases = _import_aliases(tree)
            functions = _top_level_functions(tree)
            callables = _local_callables(tree)
            module_callables = _module_callable_names(tree)
            required = {"load_config", "validate_inputs", "build_plan", "main"}
            valid = required <= set(functions)
            if valid:
                load_nodes = _expand_local_call_graph(
                    _reachable_nodes(functions["load_config"]),
                    callables,
                    aliases,
                    available_callables=module_callables,
                )
                validate_nodes = _expand_local_call_graph(
                    _reachable_nodes(functions["validate_inputs"]),
                    callables,
                    aliases,
                    available_callables=module_callables,
                )
                plan_nodes = _expand_local_call_graph(
                    _reachable_nodes(functions["build_plan"]),
                    callables,
                    aliases,
                    available_callables=module_callables,
                )
                main_direct_nodes = _reachable_nodes(functions["main"], dry_run=True)
                main_nodes = _expand_local_call_graph(
                    main_direct_nodes,
                    callables,
                    aliases,
                    dry_run=True,
                    available_callables=module_callables,
                )
                module_nodes = _expand_local_call_graph(
                    _reachable_nodes(tree, constants={"__name__": "__main__"}),
                    callables,
                    aliases,
                    available_callables=module_callables,
                )
                load_calls = _call_names(load_nodes, aliases)
                validate_calls = _call_names(validate_nodes, aliases)
                validate_literals = _node_literals(validate_nodes)
                plan_literals = _node_literals(plan_nodes)
                main_calls = _call_names(main_nodes, aliases)
                main_literals = _node_literals(main_direct_nodes)
                valid = (
                    any(name in {"json.load", "json.loads"} for name in load_calls)
                    and any(name.split(".")[-1] in {"open", "read_text"} for name in load_calls)
                    and {"input_contract", "required_paths", "required_fields"}
                    <= validate_literals
                    and any(
                        name in {"json.load", "json.loads"}
                        for name in validate_calls
                    )
                    and any(
                        name.split(".")[-1] in {"open", "read_text"}
                        for name in validate_calls
                    )
                    and any(
                        isinstance(node, ast.Raise)
                        for node in validate_nodes
                    )
                    and {"split_strategy", "metrics", "baselines", "seeds"}
                    <= plan_literals
                    and any(
                        isinstance(node, ast.Return) and node.value is not None
                        for node in plan_nodes
                    )
                    and {"load_config", "validate_inputs", "build_plan"}
                    <= {name.split(".")[-1] for name in main_calls}
                    and {"--config", "--dry-run"} <= main_literals
                    and any(
                        isinstance(node, ast.If)
                        and any(
                            (name := _dotted_name(child)) is not None
                            and re.search(r"dry_?run", name, re.IGNORECASE)
                            for child in ast.walk(node.test)
                        )
                        for node in main_direct_nodes
                    )
                    and any(
                        isinstance(node, ast.Call)
                        and _resolved_call_name(node.func, aliases) == "main"
                        for node in module_nodes
                    )
                )
            if not valid:
                _issue(
                    issues,
                    "missing_entrypoint_contract",
                    main_path,
                    "main.py must load config, validate input contracts, build the plan, expose --dry-run, and invoke main",
                )

    smoke_path = "experiment/code/tests/test_smoke.py"
    smoke_source = outputs.get(smoke_path)
    if isinstance(smoke_source, str):
        try:
            smoke_tree = ast.parse(smoke_source, filename=smoke_path)
        except SyntaxError:
            smoke_tree = None
        if smoke_tree is not None:
            aliases = _import_aliases(smoke_tree)
            functions = _top_level_functions(smoke_tree)
            callables = _local_callables(smoke_tree)
            module_callables = _module_callable_names(smoke_tree)
            module_nodes = _reachable_nodes(smoke_tree)
            imported = {
                alias.name
                for node in module_nodes
                if isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.endswith("main")
                for alias in node.names
            }
            required = {"load_config", "validate_inputs", "build_plan", "main"}
            valid = required <= imported and any(
                required
                <= {
                    name.rsplit(".", maxsplit=1)[-1]
                    for name in _call_names(nodes, aliases)
                }
                and "--dry-run" in _node_literals(nodes)
                for name, function in functions.items()
                if name.startswith("test_")
                for nodes in (
                    _expand_local_call_graph(
                        _reachable_nodes(function),
                        callables,
                        aliases,
                        available_callables=module_callables,
                    ),
                )
            )
            if not valid:
                _issue(
                    issues,
                    "missing_smoke_contract",
                    smoke_path,
                    "smoke test must import and exercise config, input, plan, and dry-run readiness",
                )


def _validate_commands(
    manifest: dict[str, Any], readme: object, issues: list[ComputationalPackageIssue]
) -> None:
    if manifest.get("commands") != _EXPECTED_COMMANDS:
        _issue(
            issues,
            "command_mismatch",
            MANIFEST_PATH,
            "commands must equal the declared dry-run and smoke-test commands",
        )
    if not isinstance(readme, str) or any(command not in readme for command in _EXPECTED_COMMANDS.values()):
        _issue(
            issues,
            "command_mismatch",
            _README_PATH,
            "README must contain the declared dry-run and smoke-test commands",
        )


def validate_computational_package(
    root: Path,
    design_json: str,
    outputs: Mapping[str, str],
    project_id: str,
    *,
    approved_design_sha256: str | None = None,
    prepared_snapshot: tuple[FilesystemEntry, ...] | None = None,
    authorized_paths: frozenset[str] = frozenset(),
) -> tuple[ComputationalPackageIssue, ...]:
    """Validate package structure without importing or executing package code.

    ``approved_design_sha256`` binds the package to the exact approved design
    bytes when the caller has read that durable artifact from disk.
    """
    issues: list[ComputationalPackageIssue] = []
    for path in REQUIRED_OUTPUTS:
        if not isinstance(outputs.get(path), str):
            _issue(issues, "missing_artifact", path, "required artifact is missing")

    manifest = _parse_object(outputs.get(MANIFEST_PATH), MANIFEST_PATH, issues)
    config_path = "experiment/code/config.json"
    config = _parse_object(outputs.get(config_path), config_path, issues)
    design_sha256 = approved_design_sha256 or hashlib.sha256(
        design_json.encode("utf-8")
    ).hexdigest()
    try:
        design = json.loads(design_json)
    except json.JSONDecodeError:
        design = None

    if manifest is not None:
        _validate_closed_fields(manifest, MANIFEST_FIELDS, MANIFEST_PATH, "manifest", issues)
        if not _is_schema_version(manifest.get("schema_version")):
            _issue(issues, "invalid_format", MANIFEST_PATH, "schema_version must equal 1")
        if manifest.get("project_id") != project_id:
            _issue(issues, "project_mismatch", MANIFEST_PATH, "project_id must match durable state")
        if manifest.get("design_sha256") != design_sha256:
            _issue(
                issues,
                "design_mismatch",
                MANIFEST_PATH,
                "design_sha256 must match the approved design",
            )
        if manifest.get("validation_type") != "computational":
            _issue(
                issues,
                "invalid_format",
                MANIFEST_PATH,
                "validation_type must be computational",
            )
        if manifest.get("entry_point") != "experiment/code/main.py":
            _issue(issues, "invalid_format", MANIFEST_PATH, "entry_point must be main.py")
        if manifest.get("config_path") != config_path:
            _issue(issues, "invalid_format", MANIFEST_PATH, "config_path must be config.json")
        _validate_commands(manifest, outputs.get(_README_PATH), issues)
        declared_hashes = _validate_manifest_files(manifest, issues)
        _validate_hashes(root, declared_hashes, issues)
        _validate_manifest_contracts(
            manifest, config, design_sha256, issues
        )

    if config is not None:
        _validate_closed_fields(config, CONFIG_FIELDS, config_path, "config", issues)
        if not _is_schema_version(config.get("schema_version")):
            _issue(issues, "invalid_format", config_path, "schema_version must equal 1")
        if config.get("project_id") != project_id:
            _issue(issues, "project_mismatch", config_path, "project_id must match durable state")
        if config.get("design_sha256") != design_sha256:
            _issue(
                issues,
                "design_mismatch",
                config_path,
                "design_sha256 must match the approved design",
            )
        _validate_traceability(design_json, config, issues)
        _validate_config_contract(design, config, issues)

    _validate_on_disk_tree(root, prepared_snapshot, authorized_paths, issues)
    _validate_python_syntax(outputs, issues)
    _validate_python_capabilities(outputs, issues)
    _validate_python_contracts(outputs, issues)
    _validate_requirements(outputs.get(_REQUIREMENTS_PATH), issues)
    return tuple(issues)
