import json
import subprocess
import sys

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
from tests.codex_native.helpers import (
    build_completed_validation_design_project,
    build_stage_twelve_project,
)


def _remove_stage_ten_snapshot(project):
    state_path = project.root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.pop("stage_10_snapshot", None)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def test_init_then_status_outputs_machine_readable_json(tmp_path, capsys):
    root = tmp_path / "demo"

    assert main(["init", str(root), "--topic", "Formation energy", "--profile", "materials_ai", "--json"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["status"] == "ready"

    assert main(["status", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_stage"] == 1
    assert payload["status"] == "ready"


def test_json_errors_keep_stdout_empty(tmp_path, capsys):
    exit_code = main(["status", str(tmp_path / "missing"), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "state.json" in captured.err


def test_json_status_normalizes_malformed_state_to_stderr(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["init", str(root), "--topic", "Formation energy", "--json"]) == 0
    capsys.readouterr()
    state_path = root / ".researchclaw" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    del state["project_id"]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert main(["status", str(root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "project_id" in captured.err


def test_module_help_uses_the_public_codex_cli_name():
    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("usage: researchclaw-codex ")


def test_stage_prepare_cli_keeps_legacy_baseline_migration_opt_in(tmp_path, capsys):
    project = build_completed_validation_design_project(tmp_path / "project")
    _remove_stage_ten_snapshot(project)

    assert main(["stage", "prepare", str(project.root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "legacy Stage 10" in captured.err
    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "legacy_missing"


def test_stage_prepare_cli_explicitly_establishes_safe_legacy_baseline(
    tmp_path, capsys
):
    project = build_completed_validation_design_project(tmp_path / "project")
    _remove_stage_ten_snapshot(project)

    assert main(
        [
            "stage",
            "prepare",
            str(project.root),
            "--establish-legacy-baseline",
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage_id"] == 10
    assert ResearchProject.open(project.root).state.stage_10_snapshot.status == "captured"


def test_execution_recheck_cli_refreshes_declared_readiness(tmp_path, capsys):
    project, declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")

    assert main(["execution", "recheck", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "ready_for_execution"
    assert payload["approval_eligible"] is True
    assert payload["unmet_prerequisites"] == []
    assert len(payload["resource_plan_sha256"]) == 64
    assert captured.err == ""
    assert not (project.root / "experiment/results.json").exists()


@pytest.mark.parametrize("command", ["approve", "recheck"])
@pytest.mark.parametrize(
    ("lineage_damage", "expected_stage"),
    [
        ("tampered-package-file", 10),
        ("missing-stage-nine-approval", 9),
        ("rejected-stage-nine-approval", 9),
    ],
)
def test_stage_twelve_cli_commands_normalize_durable_lineage_before_mutating(
    tmp_path,
    capsys,
    command,
    lineage_damage,
    expected_stage,
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / f"{command}-{lineage_damage}"
    )
    if lineage_damage == "tampered-package-file":
        main_path = project.root / "experiment/code/main.py"
        main_path.write_bytes(main_path.read_bytes() + b"\n# tampered after validation\n")
    else:
        approval_path = project.root / "approvals/stage-09.json"
        if lineage_damage == "missing-stage-nine-approval":
            approval_path.unlink()
        else:
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            approval["decision"] = "reject"
            approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")

    argv = (
        ["approve", str(project.root), "--decision", "approve", "--json"]
        if command == "approve"
        else ["execution", "recheck", str(project.root), "--json"]
    )
    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    state = ResearchProject.open(project.root).state
    assert state.current_stage == expected_stage
    assert state.status.value == "needs_revision"
    assert state.next_action == "validate_stage"
    assert not (project.root / "approvals/stage-12.json").exists()
