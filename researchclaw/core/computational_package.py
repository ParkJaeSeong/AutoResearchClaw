"""Pure structural validation for stage-10 computational packages."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping


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
)
_FAKE_RESULT_NAME = re.compile(
    r"(?:synthetic|fake|dummy)[_\s-]*(?:result|results|output|outputs|metric|metrics|prediction|predictions)",
    re.IGNORECASE,
)
_TRACEABILITY_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


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
        _normalized_distribution_name(forbidden) for forbidden in _FORBIDDEN_IMPORTS
    }


def _absolute_literal(value: object) -> bool:
    return (
        isinstance(value, str)
        and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute())
    )


def _assignment_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(name for element in node.elts for name in _assignment_names(element))
    return ()


def _smoke_test_writes_artifacts(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name is None:
            continue
        if name.split(".")[-1] in {
            "write_text",
            "write_bytes",
            "touch",
            "replace",
            "rename",
            "unlink",
            "dump",
        }:
            return True
        if name in {"open", "io.open"}:
            mode = next(
                (
                    keyword.value.value
                    for keyword in node.keywords
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ),
                node.args[1].value
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                else "r",
            )
            if any(marker in mode for marker in "wax+"):
                return True
    return False


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


def _resolved_call_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    name = _dotted_name(node)
    if name is None:
        return None
    root, *remainder = name.split(".")
    target = aliases.get(root)
    return ".".join((target, *remainder)) if target is not None else name


def _forbidden_call(name: str | None) -> bool:
    return (
        name in {
            "os.system",
            "os.popen",
            "eval",
            "exec",
            "builtins.eval",
            "builtins.exec",
            "__builtins__.eval",
            "__builtins__.exec",
            "__import__",
            "builtins.__import__",
            "__builtins__.__import__",
        }
        or (name is not None and name.startswith("subprocess."))
    )


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
                forbidden = forbidden or _forbidden_call(_resolved_call_name(node.func, aliases))
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                fake_result_assignment = fake_result_assignment or any(
                    _FAKE_RESULT_NAME.search(name) is not None
                    for target in targets
                    for name in _assignment_names(target)
                )
            if isinstance(node, ast.Constant) and _absolute_literal(node.value):
                unsafe_path = True

        if fake_result_assignment and not (
            path == "experiment/code/tests/test_smoke.py"
            and not _smoke_test_writes_artifacts(tree)
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
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        match = _REQUIREMENT_NAME.match(line)
        requirement_name = match.group(1).lower() if match else ""
        if requirement_name and _forbidden_distribution(requirement_name):
            _issue(
                issues,
                "forbidden_capability",
                _REQUIREMENTS_PATH,
                f"requirements line {line_number} declares a prohibited dependency",
            )
        bounded = bool(re.search(r"(?:==|~=)\s*[^\s,;]+", line)) or (
            re.search(r">=?\s*[^\s,;]+", line) is not None
            and re.search(r"<=?\s*[^\s,;]+", line) is not None
        )
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


def _validate_traceability(
    design_json: str, config: dict[str, Any], issues: list[ComputationalPackageIssue]
) -> None:
    try:
        design = json.loads(design_json)
    except json.JSONDecodeError:
        design = None
    traceability = config.get("traceability")
    if not isinstance(traceability, dict) or any(
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

    _validate_python_syntax(outputs, issues)
    _validate_python_capabilities(outputs, issues)
    _validate_requirements(outputs.get(_REQUIREMENTS_PATH), issues)
    return tuple(issues)
