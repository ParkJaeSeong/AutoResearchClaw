"""Pure structural validation for stage-10 computational packages."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
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


def validate_computational_package(
    root: Path,
    design_json: str,
    outputs: Mapping[str, str],
    project_id: str,
) -> tuple[ComputationalPackageIssue, ...]:
    """Validate package structure without importing or executing package code."""
    issues: list[ComputationalPackageIssue] = []
    for path in REQUIRED_OUTPUTS:
        if not isinstance(outputs.get(path), str):
            _issue(issues, "missing_artifact", path, "required artifact is missing")

    manifest = _parse_object(outputs.get(MANIFEST_PATH), MANIFEST_PATH, issues)
    config_path = "experiment/code/config.json"
    config = _parse_object(outputs.get(config_path), config_path, issues)
    design_sha256 = hashlib.sha256(design_json.encode("utf-8")).hexdigest()

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

    _validate_python_syntax(outputs, issues)
    return tuple(issues)
