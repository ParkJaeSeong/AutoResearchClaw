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


def _replace_config(project, mutate):
    config_path = "experiment/code/config.json"
    config = json.loads((project.root / config_path).read_text(encoding="utf-8"))
    mutate(config)
    _replace_package_file(project, config_path, json.dumps(config) + "\n")


def _replace_manifest(project, mutate):
    manifest_path = project.root / "experiment" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
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


def test_valid_stage_ten_stops_before_unsupported_stage_eleven(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)

    report = validate_current_stage(project)

    state = ResearchProject.open(project.root).state
    assert report.valid is True
    assert report.recommended_action == "report_computational_package_milestone_only"
    assert state.current_stage == 11
    assert state.completed_stages == tuple(range(1, 11))
    assert state.next_action == "report_computational_package_milestone_only"
    with pytest.raises(ValueError, match="not defined"):
        build_task_packet(ResearchProject.open(project.root))


def test_stage_ten_completion_handoff_reports_the_computational_package_only(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    assert validate_current_stage(project).valid is True

    handoff = ResearchProject.open(project.root).build_handoff()

    assert handoff.milestone_complete is True
    assert handoff.next_action == "report_computational_package_milestone_only"
    assert handoff.next_command.split()[1] == "evaluate"
    assert handoff.write_policy == "no_undeclared_outputs"


def test_changed_approved_design_rewinds_and_invalidates_package_lineage(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    assert validate_current_stage(project).valid is True
    design_path = project.root / "experiment" / "design.json"
    design_path.write_text(design_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    handoff = ResearchProject.open(project.root).build_handoff()

    state = ResearchProject.open(project.root).state
    assert handoff.current_stage == 9
    assert handoff.next_action == "validate_stage"
    assert state.completed_stages == tuple(range(1, 9))
    assert state.last_error["issues"][0]["code"] == "approval_invalidated"
    assert not {
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/README.md",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/code/requirements.txt",
        "experiment/code/tests/test_smoke.py",
    }.intersection(state.artifacts)


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
        ("import os as runner\nrunner.system('x')", "forbidden_capability"),
        ("from os import system as shell\nshell('x')", "forbidden_capability"),
        ("from os import popen as reader\nreader('x')", "forbidden_capability"),
        ("from builtins import eval as evaluate\nevaluate('1 + 1')", "forbidden_capability"),
        ("from builtins import exec as execute\nexecute('x = 1')", "forbidden_capability"),
        ("__import__('openai')", "forbidden_capability"),
        ("Path('/tmp/result.json')", "unsafe_path"),
        ("import os\nos.path.join('/tmp', 'result.json')", "unsafe_path"),
        ("result_path = '/tmp/result.json'", "unsafe_path"),
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


@pytest.mark.parametrize(
    "requirement",
    [
        "google-generativeai==0.8.5",
        "semantic-kernel==1.0.0",
        "pydantic-ai==0.0.1",
        "haystack-ai==2.0.0",
        "farm-haystack==1.0.0",
    ],
)
def test_package_rejects_normalized_forbidden_requirement_names(tmp_path, requirement):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(project, "experiment/code/requirements.txt", f"{requirement}\n")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "forbidden_capability"
        and issue.path == "experiment/code/requirements.txt"
        for issue in report.issues
    )


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


def test_package_rejects_traceability_to_unrelated_design_fields(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    config_path = "experiment/code/config.json"
    config = json.loads((project.root / config_path).read_text(encoding="utf-8"))
    config["traceability"] = {
        field: "title"
        for field in (
            "datasets",
            "baselines",
            "split_strategy",
            "metrics",
            "seeds",
            "input_contract",
            "output_contract",
        )
    }
    _replace_package_file(project, config_path, json.dumps(config) + "\n")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "missing_traceability" and issue.path == config_path
        for issue in report.issues
    )


def test_package_rejects_empty_config_sections_despite_traceability(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    config_path = "experiment/code/config.json"
    config = json.loads((project.root / config_path).read_text(encoding="utf-8"))
    config.update(
        {
            "datasets": [],
            "baselines": [],
            "split_strategy": "",
            "metrics": [],
            "seeds": [],
            "input_contract": {},
            "output_contract": {},
        }
    )
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


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\nos.spawnvp(os.P_NOWAIT, 'sh', ['sh', '-c', 'true'])",
        "import os\nos.posix_spawn('/bin/sh', ['sh'], {})",
        "import os\nos.execvp('sh', ['sh'])",
        "import asyncio\nasyncio.create_subprocess_shell('true')",
        "from asyncio import create_subprocess_exec\ncreate_subprocess_exec('true')",
        "import os\ngetattr(os, 'spawnvp')(os.P_NOWAIT, 'sh', ['sh'])",
        "import os\nos.__dict__['system']('true')",
        "import importlib\nimportlib.import_module('litellm')",
    ],
    ids=(
        "os-spawn",
        "os-posix-spawn",
        "os-exec",
        "asyncio-shell",
        "asyncio-exec-alias",
        "getattr-dispatch",
        "mapping-dispatch",
        "dynamic-import",
    ),
)
def test_package_rejects_process_shell_and_dynamic_dispatch_families(tmp_path, snippet):
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
        issue.code == "forbidden_capability" and issue.path == "experiment/code/main.py"
        for issue in report.issues
    )


@pytest.mark.parametrize(
    "module",
    [
        "litellm",
        "ftplib",
        "http.client",
        "aiohttp",
        "multiprocessing",
        "llama_index",
    ],
)
def test_package_rejects_network_llm_and_agent_import_families(tmp_path, module):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project,
        "experiment/code/main.py",
        f"import {module}\n\ndef main() -> None:\n    return None\n",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "forbidden_capability" and issue.path == "experiment/code/main.py"
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("relative_path", "source"),
    [
        (
            "experiment/code/tests/test_smoke.py",
            "from pathlib import Path\n\ndef test_smoke():\n"
            "    Path('experiment/results.json').write_text('{}')\n",
        ),
        (
            "experiment/code/tests/test_smoke.py",
            "def test_smoke():\n"
            "    with open('experiment/results.json', 'w') as handle:\n"
            "        handle.write('{}')\n",
        ),
        (
            "experiment/code/main.py",
            "from pathlib import Path\n\ndef dry_run():\n"
            "    Path('experiment/results.json').write_text('{}')\n\n"
            "def main() -> None:\n    dry_run()\n",
        ),
    ],
    ids=("smoke-path-write", "smoke-open-write", "dry-run-result-write"),
)
def test_package_rejects_smoke_or_dry_run_artifact_writes(
    tmp_path, relative_path, source
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(project, relative_path, source)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "forbidden_capability" and issue.path == relative_path
        for issue in report.issues
    )


@pytest.mark.parametrize(
    "requirement",
    [
        "evil @ https://example.invalid/pkg.whl?release==1.0",
        "evil @ git+https://example.invalid/repo.git@v1.0.0",
        "https://example.invalid/pkg.whl",
        "git+ssh://git@example.invalid/repo.git@v1.0.0",
        "-r other-requirements.txt",
        "--index-url https://example.invalid/simple",
        "-e git+https://example.invalid/repo.git#egg=evil",
    ],
)
def test_package_rejects_direct_url_vcs_and_option_requirements(tmp_path, requirement):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project, "experiment/code/requirements.txt", f"{requirement}\n"
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "forbidden_dependency_source"
        and issue.path == "experiment/code/requirements.txt"
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("datasets", ["unapproved private dataset"]),
        ("baselines", ["unapproved oracle"]),
        ("metrics", [{"name": "accuracy", "target": "at least 99%"}]),
    ],
)
def test_package_rejects_config_values_not_bound_to_approved_design(
    tmp_path, field, replacement
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_config(project, lambda config: config.update({field: replacement}))

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "config_design_mismatch" for issue in report.issues)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("split_strategy", "train and test may share rows"),
        ("seeds", ["17"]),
        ("input_contract", {"required_paths": []}),
        ("output_contract", {"result_path": "experiment/results.json"}),
    ],
)
def test_package_rejects_untyped_or_nonisolated_config_contracts(
    tmp_path, field, replacement
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_config(project, lambda config: config.update({field: replacement}))

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_config_contract" for issue in report.issues)


def test_package_requires_exact_traceability_keys(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_config(
        project,
        lambda config: config["traceability"].update({"undeclared": "title"}),
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "missing_traceability" for issue in report.issues)


def test_package_rejects_noop_main_entry_point(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project,
        "experiment/code/main.py",
        "def main() -> None:\n    return None\n",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "missing_entrypoint_contract" for issue in report.issues)


def test_package_requires_input_schema_validation_in_entry_point(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    main_path = project.root / "experiment" / "code" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    source = source.replace(
        "        with candidate.open(encoding='utf-8') as handle:\n"
        "            record = json.load(handle)\n"
        "        if not isinstance(record, dict) or any(\n"
        "            field not in record for field in required_fields\n"
        "        ):\n"
        "            raise ValueError('input schema does not match contract')\n",
        "",
    )
    _replace_package_file(project, "experiment/code/main.py", source)

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "missing_entrypoint_contract" for issue in report.issues)


def test_package_rejects_smoke_test_that_does_not_exercise_readiness(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_package_file(
        project,
        "experiment/code/tests/test_smoke.py",
        "def test_smoke_contract():\n    assert True\n",
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "missing_smoke_contract" for issue in report.issues)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("runtime", {}),
        ("input_contract", {}),
        ("output_contract", {}),
        ("prohibitions", []),
        ("reproducibility", {}),
    ],
)
def test_package_rejects_empty_manifest_contracts(tmp_path, field, replacement):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_manifest(project, lambda manifest: manifest.update({field: replacement}))

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_manifest_contract" for issue in report.issues)


def test_package_rejects_undeclared_nested_manifest_contract_fields(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    _replace_manifest(
        project,
        lambda manifest: manifest["runtime"].update({"shell": "bash"}),
    )

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(issue.code == "invalid_manifest_contract" for issue in report.issues)


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiment/code/undeclared.py",
        "experiment/code/analysis.ipynb",
        "experiment/code/downloads/data.csv",
        "experiment/results.json",
        "experiment/results/run.json",
        "experiment/downloads/data.csv",
        "results.json",
        "results/run.json",
        "downloads/data.csv",
        "data/downloaded.csv",
    ],
)
def test_package_rejects_undeclared_results_and_download_artifacts(
    tmp_path, relative_path
):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    artifact = project.root / relative_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("untrusted", encoding="utf-8")

    report = validate_current_stage(project)

    assert report.valid is False
    assert any(
        issue.code == "undeclared_artifact" and issue.path == relative_path
        for issue in report.issues
    )


def test_package_allows_absolute_prefix_guard_outside_filesystem_sink(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    main_path = project.root / "experiment" / "code" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    source += (
        "\ndef reject_absolute(value: str) -> None:\n"
        "    if value.startswith('/'):\n"
        "        raise ValueError('absolute paths are forbidden')\n"
    )
    _replace_package_file(project, "experiment/code/main.py", source)

    report = validate_current_stage(project)

    assert report.valid is True
