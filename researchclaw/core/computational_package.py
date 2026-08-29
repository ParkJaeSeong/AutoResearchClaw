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

from .filesystem_baseline import snapshot_project_paths


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
_FORBIDDEN_IMPORTS = (
    "openai",
    "anthropic",
    "google.generativeai",
    "google.genai",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "subprocess",
    "langchain",
    "autogen",
    "crewai",
    "pydantic_ai",
    "semantic_kernel",
    "haystack",
    "litellm",
    "cohere",
    "mistralai",
    "groq",
    "together",
    "ollama",
    "llama_index",
    "smolagents",
    "ftplib",
    "http",
    "aiohttp",
    "urllib3",
    "websockets",
    "smtplib",
    "imaplib",
    "poplib",
    "telnetlib",
    "xmlrpc.client",
    "paramiko",
    "multiprocessing",
    "ctypes",
)
_FORBIDDEN_DISTRIBUTIONS = (
    *_FORBIDDEN_IMPORTS,
    "google-genai",
    "haystack-ai",
    "farm-haystack",
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
    prepared_paths: tuple[str, ...] | None,
    issues: list[ComputationalPackageIssue],
) -> None:
    if prepared_paths is None:
        _issue(
            issues,
            "missing_prepare_baseline",
            MANIFEST_PATH,
            "stage 10 must be prepared before its outputs are authored",
        )
        return
    baseline = set(prepared_paths)
    current = set(snapshot_project_paths(root))
    expected_additions = set(REQUIRED_OUTPUTS)
    for relative in sorted((current - baseline) - expected_additions):
        _issue(
            issues,
            "undeclared_artifact",
            relative,
            "filesystem paths added after Stage 10 prepare must be declared outputs",
        )
    for relative in sorted(baseline - current):
        _issue(
            issues,
            "undeclared_artifact",
            relative,
            "filesystem paths present at Stage 10 prepare must not be removed",
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


def _forbidden_import(name: str) -> bool:
    return any(name == forbidden or name.startswith(f"{forbidden}.") for forbidden in _FORBIDDEN_IMPORTS)


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _forbidden_distribution(name: str) -> bool:
    return _normalized_distribution_name(name) in {
        _normalized_distribution_name(forbidden) for forbidden in _FORBIDDEN_DISTRIBUTIONS
    }


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
    return root not in {
        "Path",
        "pathlib.Path",
        "PurePath",
        "pathlib.PurePath",
        "PurePosixPath",
        "pathlib.PurePosixPath",
        "PureWindowsPath",
        "pathlib.PureWindowsPath",
    }


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


class _ReachableNodeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def visit_block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self.visit(statement)
            if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                break

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.nodes.append(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.nodes.append(node)

    def visit_If(self, node: ast.If) -> None:
        self.nodes.append(node)
        self.visit(node.test)
        if isinstance(node.test, ast.Constant):
            branch = node.body if bool(node.test.value) else node.orelse
            self.visit_block(branch)
        else:
            self.visit_block(node.body)
            self.visit_block(node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self.nodes.append(node)
        self.visit(node.test)
        if not isinstance(node.test, ast.Constant) or bool(node.test.value):
            self.visit_block(node.body)
        self.visit_block(node.orelse)


def _reachable_nodes(node: ast.AST) -> list[ast.AST]:
    collector = _ReachableNodeCollector()
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
        collector.visit_block(node.body)
    else:
        collector.visit(node)
    return collector.nodes


def _top_level_functions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _expand_local_call_graph(
    initial_nodes: list[ast.AST],
    functions: Mapping[str, ast.FunctionDef | ast.AsyncFunctionDef],
    aliases: Mapping[str, str],
) -> list[ast.AST]:
    expanded = list(initial_nodes)
    queued = [
        name.rsplit(".", maxsplit=1)[-1]
        for node in initial_nodes
        if isinstance(node, ast.Call)
        and (name := _resolved_call_name(node.func, aliases)) is not None
    ]
    visited: set[str] = set()
    while queued:
        function_name = queued.pop()
        if function_name in visited or function_name not in functions:
            continue
        visited.add(function_name)
        nodes = _reachable_nodes(functions[function_name])
        expanded.extend(nodes)
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
    for name, function in functions.items():
        if not name.startswith("test_"):
            continue
        nodes = _expand_local_call_graph(
            _reachable_nodes(function), functions, aliases
        )
        if _nodes_write_artifacts(nodes, aliases):
            return True
    return False


def _dry_run_reaches_artifact_write(
    tree: ast.Module, aliases: Mapping[str, str]
) -> bool:
    functions = _top_level_functions(tree)
    main = functions.get("main")
    if main is None:
        return False
    main_nodes = _expand_local_call_graph(_reachable_nodes(main), functions, aliases)
    called_functions = {
        name.rsplit(".", maxsplit=1)[-1]
        for name in _call_names(main_nodes, aliases)
    }
    for name, function in functions.items():
        if (
            name in called_functions
            and re.search(r"dry_?run", name, re.IGNORECASE)
            and _nodes_write_artifacts(
                _expand_local_call_graph(
                    _reachable_nodes(function), functions, aliases
                ),
                aliases,
            )
        ):
            return True
    for node in _reachable_nodes(main):
        if not isinstance(node, ast.If):
            continue
        test_names = {
            name
            for child in ast.walk(node.test)
            if (name := _dotted_name(child)) is not None
        }
        if not any(re.search(r"dry_?run", name, re.IGNORECASE) for name in test_names):
            continue
        collector = _ReachableNodeCollector()
        collector.visit_block(node.body)
        branch_nodes = _expand_local_call_graph(
            collector.nodes, functions, aliases
        )
        if _nodes_write_artifacts(branch_nodes, aliases):
            return True
    return False


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
        if not _forbidden_call(resolved):
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
        forbidden = False
        unsafe_path = False
        fake_result_assignment = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                forbidden = forbidden or any(_forbidden_import(alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                forbidden = forbidden or (
                    node.module is not None
                    and (
                        _forbidden_import(node.module)
                        or any(
                            _forbidden_import(f"{node.module}.{alias.name}")
                            for alias in node.names
                        )
                    )
                )
            elif isinstance(node, ast.Call):
                forbidden = forbidden or _forbidden_call(
                    _resolved_call_name(node.func, aliases)
                ) or _call_is_dynamic_dispatch(node, aliases)
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
        if _forbidden_distribution(requirement.name):
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
            required = {"load_config", "validate_inputs", "build_plan", "main"}
            valid = required <= set(functions)
            if valid:
                load_nodes = _reachable_nodes(functions["load_config"])
                validate_nodes = _reachable_nodes(functions["validate_inputs"])
                plan_nodes = _reachable_nodes(functions["build_plan"])
                main_direct_nodes = _reachable_nodes(functions["main"])
                main_nodes = _expand_local_call_graph(
                    main_direct_nodes, functions, aliases
                )
                module_nodes = _reachable_nodes(tree)
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
                        _reachable_nodes(function), functions, aliases
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
    prepared_paths: tuple[str, ...] | None = None,
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

    _validate_on_disk_tree(root, prepared_paths, issues)
    _validate_python_syntax(outputs, issues)
    _validate_python_capabilities(outputs, issues)
    _validate_python_contracts(outputs, issues)
    _validate_requirements(outputs.get(_REQUIREMENTS_PATH), issues)
    return tuple(issues)
