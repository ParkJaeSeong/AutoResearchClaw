import hashlib
import json

import pytest

from researchclaw.core.approval import approve_current_gate
from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import build_task_packet
from researchclaw.core.validation import validate_current_stage

from tests.codex_native.helpers import (
    build_completed_hypothesis_milestone_project,
    build_completed_validation_design_project,
    write_valid_fixture_artifacts,
)


def _replace_package_file(project, relative_path, content):
    path = project.root / relative_path
    path.write_text(content, encoding="utf-8")
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for file_entry in manifest["files"]:
        if file_entry["path"] == relative_path:
            file_entry["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            break
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")


def test_stage_ten_packet_declares_fixed_computational_package(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")

    packet = build_task_packet(project)

    assert packet.stage_id == 10
    assert packet.name == "code_generation"
    assert packet.required_inputs == ("experiment/design.json",)
    assert packet.required_outputs == (
        "experiment/package_manifest.json",
        "experiment/code/README.md",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/code/requirements.txt",
        "experiment/code/tests/test_smoke.py",
    )
    assert packet.allowed_tool_classes == ("filesystem", "analysis")
    assert packet.requires_approval is False


@pytest.mark.parametrize("validation_type", ["policy_evidence", "laboratory"])
def test_stage_ten_rejects_deferred_validation_types(tmp_path, validation_type):
    project = build_completed_validation_design_project(
        tmp_path / "project", validation_type=validation_type
    )

    with pytest.raises(ValueError, match=f"stage 10 does not support {validation_type}"):
        build_task_packet(project)


def test_stage_ten_requires_current_stage_nine_approval(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    (project.root / "approvals" / "stage-09.json").unlink()

    with pytest.raises(
        ValueError, match="stage 10 requires the approved stage-9 validation design"
    ):
        build_task_packet(project)


def test_open_migrates_stage_ten_validation_design_report_to_prepare(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_action"] = "report_validation_design_milestone_only"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    reopened = ResearchProject.open(project.root)

    assert reopened.state.current_stage == 10
    assert reopened.state.next_action == "prepare_stage"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["next_action"] == "prepare_stage"


def test_valid_computational_package_is_structurally_valid(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)

    report = validate_current_stage(project)

    assert report.valid is True
    assert set(report.artifact_refs) == {
        "experiment/package_manifest.json",
        "experiment/code/README.md",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/code/requirements.txt",
        "experiment/code/tests/test_smoke.py",
    }


def test_package_binds_design_sha256_to_approved_crlf_bytes(tmp_path):
    project = build_completed_hypothesis_milestone_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 9)
    design_path = project.root / "experiment" / "design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design["validation_type"] = "computational"
    design["method"] = {
        "datasets": ["versioned public battery dataset"],
        "split_strategy": "cell-grouped held-out test split",
        "baselines": ["random row split"],
        "evaluation_protocol": "fit preprocessing on train only",
    }
    design_path.write_bytes((json.dumps(design) + "\r\n").encode("utf-8"))
    assert validate_current_stage(project).valid is True
    approve_current_gate(ResearchProject.open(project.root), "approve", "CRLF design accepted")
    project = ResearchProject.open(project.root)
    write_valid_fixture_artifacts(project.root, 10)

    report = validate_current_stage(project)

    assert report.valid is True


def test_package_rejects_wrong_design_hash_or_project_id(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["design_sha256"] = "0" * 64
    manifest["project_id"] = "another-project"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "design_mismatch",
        "project_mismatch",
    }


def test_package_rejects_missing_extra_or_modified_manifest_files(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = manifest["files"][:-1] + [
        {
            "path": "experiment/code/extra.py",
            "role": "undeclared",
            "sha256": "0" * 64,
        }
    ]
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (project.root / "experiment" / "code" / "main.py").write_text(
        "print('changed')\n", encoding="utf-8"
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "manifest_file_set",
        "hash_mismatch",
    }


def test_package_rejects_python_syntax_error(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    (project.root / "experiment" / "code" / "main.py").write_text(
        "def broken(:\n", encoding="utf-8"
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_python" for issue in report.issues)


@pytest.mark.parametrize(
    ("artifact", "field", "mutator", "expected_code"),
    [
        ("experiment/package_manifest.json", "undeclared", lambda value: "unexpected", "unknown_field"),
        ("experiment/package_manifest.json", "runtime", lambda value: None, "missing_required_field"),
        ("experiment/code/config.json", "undeclared", lambda value: "unexpected", "unknown_field"),
        ("experiment/code/config.json", "datasets", lambda value: None, "missing_required_field"),
    ],
    ids=("manifest-extra", "manifest-missing", "config-extra", "config-missing"),
)
def test_package_rejects_nonclosed_manifest_or_config_fields(
    tmp_path, artifact, field, mutator, expected_code
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    path = project.root / artifact
    value = json.loads(path.read_text(encoding="utf-8"))
    replacement = mutator(value.get(field))
    if replacement is None:
        value.pop(field)
    else:
        value[field] = replacement
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == expected_code and issue.path == artifact for issue in report.issues)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda files: files[0].update({"undeclared": "unexpected"}),
            "unknown_field",
        ),
        (lambda files: files[0].pop("role"), "missing_required_field"),
        (
            lambda files: files[-1].update({"path": "experiment/package_manifest.json"}),
            "manifest_file_set",
        ),
        (lambda files: files.append(dict(files[0])), "manifest_file_set"),
    ],
    ids=(
        "file-entry-extra",
        "file-entry-missing",
        "manifest-self-listing",
        "duplicate-file-entry",
    ),
)
def test_package_rejects_nonclosed_or_self_listed_manifest_file_entries(
    tmp_path, mutate, expected_code
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest["files"])
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == expected_code and issue.path == "experiment/package_manifest.json"
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("snippet", "expected_code"),
    [
        ("import openai", "forbidden_capability"),
        ("import anthropic", "forbidden_capability"),
        ("from google import generativeai", "forbidden_capability"),
        ("import requests", "forbidden_capability"),
        ("import subprocess", "forbidden_capability"),
        ("os.system('x')", "forbidden_capability"),
        ("Path('/tmp/result.json')", "unsafe_path"),
        ("synthetic_results = {'rmse': 0.1}", "forbidden_capability"),
    ],
)
def test_package_rejects_forbidden_generated_code(tmp_path, snippet, expected_code):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project,
        "experiment/code/main.py",
        f"{snippet}\n\ndef main() -> None:\n    return None\n",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == expected_code and issue.path == "experiment/code/main.py"
        for issue in report.issues
    )


def test_package_rejects_unbounded_or_forbidden_requirements(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project,
        "experiment/code/requirements.txt",
        "pytest\nopenai==1.0.0\n",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "forbidden_capability",
        "unbounded_dependency",
    }


def test_package_rejects_missing_design_traceability(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    config_path = "experiment/code/config.json"
    config = json.loads((project.root / config_path).read_text(encoding="utf-8"))
    config["traceability"] = {"datasets": "method.datasets"}
    _replace_package_file(project, config_path, json.dumps(config) + "\n")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "missing_traceability" and issue.path == config_path
        for issue in report.issues
    )


def test_package_rejects_readme_manifest_command_disagreement(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commands"]["dry_run"] = "python main.py"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "command_mismatch" and issue.path == "experiment/package_manifest.json"
        for issue in report.issues
    )
