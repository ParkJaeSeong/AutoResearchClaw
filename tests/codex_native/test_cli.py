import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.project import ResearchProject
from researchclaw.core.experiment_package_contract import validate_experiment_package_contract
from researchclaw.core.research_execution import prepare_research_execution
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    build_self_test_registration_project,
    build_completed_validation_design_project,
    build_stage_twelve_project,
    load_execution_contract,
    write_runnable_development_fixture,
    write_contract_bound_research_result,
)


def _run_known_answer_self_test(project):
    package = validate_experiment_package_contract(project)
    result = subprocess.run(
        [sys.executable, "experiment/code/main.py", *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


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


def test_quarantine_result_cli_requires_confirmation_and_moves_regular_result(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)

    assert main(
        [
            "execution", "quarantine-result", str(project.root),
            "--reason", "invalid_result", "--json",
        ]
    ) == 2
    assert not capsys.readouterr().out

    assert main(
        [
            "execution", "quarantine-result", str(project.root),
            "--reason", "invalid_result", "--confirm", "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["original_path"] == "experiment/results.json"
    assert payload["reason"] == "invalid_result"
    assert not (project.root / "experiment/results.json").exists()
    assert (project.root / payload["quarantine_path"]).is_file()
    assert ResearchProject.open(project.root).build_handoff().next_action == "prepare_run"


def test_experiment_register_self_test_cli_records_external_report(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_known_answer_self_test(project)

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--confirm-self-test",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["path"] == "experiment/self_test_report.json"
    assert len(payload["sha256"]) == 64
    assert payload["size"] > 0
    assert captured.err == ""


def test_resume_cli_reports_self_test_registration_command_before_approval(
    tmp_path, capsys
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )

    assert main(["resume", str(project.root), "--json"]) == 0
    before = json.loads(capsys.readouterr().out)
    assert before["next_action"] == "register_experiment_self_test"
    assert before["approval_eligible"] is False
    assert shlex.split(before["next_command"]) == [
        "researchclaw-codex",
        "experiment",
        "register-self-test",
        str(project.root.resolve()),
        "--report",
        "experiment/self_test_report.json",
        "--confirm-self-test",
        "--json",
    ]

    _run_known_answer_self_test(ResearchProject.open(project.root))
    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--confirm-self-test",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(["resume", str(project.root), "--json"]) == 0
    after = json.loads(capsys.readouterr().out)
    assert after["next_action"] == "approve_experiment_execution"
    assert after["approval_eligible"] is True
    assert shlex.split(after["next_command"])[:2] == [
        "researchclaw-codex",
        "approve",
    ]


def test_experiment_register_self_test_cli_requires_confirmation(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")
    _run_known_answer_self_test(project)

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--confirm-self-test" in captured.err


def test_experiment_register_self_test_cli_normalizes_invalid_report(tmp_path, capsys):
    project = build_self_test_registration_project(tmp_path / "project")

    assert main(
        [
            "experiment",
            "register-self-test",
            str(project.root),
            "--report",
            "experiment/self_test_report.json",
            "--confirm-self-test",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: experiment_self_test_required\n"


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


def test_execution_recheck_cli_accepts_explicit_development_manifest(
    tmp_path, capsys
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project",
        readiness="needs_input",
    )
    fixture = project.root / "experiment/dev_data/fixture.csv"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("cell_id\nC01\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(fixture.read_bytes()).hexdigest()
    manifest = project.root / "experiment/input_manifest.dev.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "synthetic_development_input",
                "evidence_eligible": False,
                "datasets": [{"dataset_id": "SYNTH_A"}],
                "cell_records": {"path": "experiment/dev_data/fixture.csv", "row_count": 1, "sha256": digest},
                "features": {"path": "experiment/dev_data/fixture.csv", "row_count": 1, "sha256": digest},
                "labels": {"path": "experiment/dev_data/fixture.csv"},
                "groups": {"independent_group_key": "condition_id"},
                "provenance": {"license_status": "not_required_synthetic", "research_evidence_use": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(
        [
            "execution",
            "recheck",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["readiness"] == "ready_for_development"
    assert payload["approval_eligible"] is False
    assert payload["input_manifest_path"] == "experiment/input_manifest.dev.json"


def test_execution_run_cli_completes_explicit_development_fixture(tmp_path, capsys):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)

    assert main(
        [
            "execution",
            "run",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--confirm-development-run",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "development_run_complete"
    assert payload["approval_eligible"] is False
    assert captured.err == ""
    assert (project.root / "experiment/dev_results.json").exists()


def test_execution_validate_result_cli_checks_existing_development_result(
    tmp_path, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    assert main(
        [
            "execution", "run", str(project.root),
            "--input-manifest", "experiment/input_manifest.dev.json",
            "--development", "--confirm-development-run", "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "execution", "validate-result", str(project.root),
            "--result", "experiment/dev_results.json",
            "--development", "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "development_result_valid"
    assert payload["approval_eligible"] is False
    assert payload["result_path"] == "experiment/dev_results.json"
    assert len(payload["result_sha256"]) == 64
    assert captured.err == ""


def test_execution_prepare_run_cli_emits_handoff_without_running_command(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )

    assert main(["execution", "prepare-run", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    contract = load_execution_contract(project.root)
    assert payload["readiness"] == "ready_for_explicit_execution"
    assert payload["result_path"] == "experiment/results.json"
    assert payload["bindings"] == contract["bindings"]
    assert payload["inputs"] == contract["inputs"]
    assert payload["result_template"] == contract["result_template"]
    assert captured.err == ""
    assert not (project.root / "project-code-executed").exists()


def test_execution_prepare_run_cli_displays_a_quoted_argv_command(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    assert main(["execution", "prepare-run", str(project.root)]) == 0

    captured = capsys.readouterr()
    status = prepare_research_execution(ResearchProject.open(project.root))
    assert captured.out.strip() == shlex.join(status.argv)
    assert captured.err == ""


def test_execution_prepare_run_cli_rejects_unapproved_project_without_mutating_state(
    tmp_path, capsys
):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="ready_for_execution"
    )
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(["execution", "prepare-run", str(project.root), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "execution_approval_invalid" in captured.err
    assert state_path.read_bytes() == state_before
    assert not (project.root / "experiment/execution_contract.json").exists()


def test_execution_register_result_cli_advances_to_thirteen(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "research_result_registered"
    assert payload["current_stage"] == 13
    assert captured.err == ""


def test_status_cli_does_not_reuse_stage_twelve_readiness_at_stage_thirteen(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(
        project, load_execution_contract(project.root)
    )
    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(["status", str(project.root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["current_stage"] == 13
    assert payload["execution_readiness"] is None
    assert payload["unmet_prerequisites"] == []
    assert payload["approval_eligible"] is False
    assert captured.err == ""


@pytest.mark.parametrize("omitted_flag", ["--result", "--confirm-research-result"])
def test_execution_register_result_cli_requires_explicit_research_intent(
    tmp_path, capsys, omitted_flag
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()
    arguments = [
        "execution",
        "register-result",
        str(project.root),
        "--result",
        "experiment/results.json",
        "--confirm-research-result",
        "--json",
    ]
    index = arguments.index(omitted_flag)
    del arguments[index : index + (2 if omitted_flag == "--result" else 1)]

    assert main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert omitted_flag in captured.err
    assert state_path.read_bytes() == state_before


def test_execution_register_result_cli_rejects_invalid_pending_recovery_without_mutating_state(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    pending_path = (
        project.root / ".researchclaw/research-result-registration.pending.json"
    )
    pending_path.write_bytes(b'{"schema_version":3,"schema_version":3}')
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: research_result_registration_recovery_invalid\n"
    assert state_path.read_bytes() == state_before


def test_execution_register_result_cli_normalizes_malformed_event_log_without_mutating_state(
    tmp_path, capsys
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(
        project, load_execution_contract(project.root)
    )
    event_path = project.root / "evaluation/events.jsonl"
    event_path.write_bytes(event_path.read_bytes() + b"{not-json}\n")
    state_path = project.root / ".researchclaw/state.json"
    state_before = state_path.read_bytes()

    assert main(
        [
            "execution",
            "register-result",
            str(project.root),
            "--result",
            "experiment/results.json",
            "--confirm-research-result",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: research_result_registration_recovery_invalid\n"
    assert state_path.read_bytes() == state_before
    assert event_path.read_bytes().endswith(b"{not-json}\n")


def test_development_run_wrong_stage_does_not_normalize_legacy_state(tmp_path, capsys):
    project = ResearchProject.create(tmp_path / "project", "Formation energy", "materials_ai")
    _remove_stage_ten_snapshot(project)
    state_path = project.root / ".researchclaw/state.json"
    before = state_path.read_bytes()

    assert main([
        "execution", "run", str(project.root),
        "--input-manifest", "experiment/input_manifest.dev.json",
        "--development", "--confirm-development-run", "--json",
    ]) == 2

    assert state_path.read_bytes() == before
    assert "Stage 12" in capsys.readouterr().err


def test_development_run_ignores_project_local_numpy_shadow(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    marker = project.root / "numpy-shadow-executed"
    (project.root / "numpy.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "raise ImportError('project shadow must not execute')\n",
        encoding="utf-8",
    )
    repository_root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "PYTHONPATH": str(repository_root)}

    result = subprocess.run(
        [
            sys.executable, "-m", "researchclaw.codex.cli", "execution", "run",
            str(project.root), "--input-manifest", "experiment/input_manifest.dev.json",
            "--development", "--confirm-development-run", "--json",
        ],
        cwd=project.root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert json.loads(result.stdout)["readiness"] == "development_run_complete"


def test_numpy_absence_is_bounded_to_development_execution_in_fresh_process(tmp_path):
    project, _ = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    manifest = write_runnable_development_fixture(project)
    prior_result = project.root / "experiment/dev_results.json"
    prior_result.write_bytes(b'{"prior":true}\n')
    blocker = tmp_path / "blocked-import"
    blocker.mkdir()
    (blocker / "numpy.py").write_text(
        "raise ImportError('NumPy deliberately unavailable')\n", encoding="utf-8"
    )
    repository_root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(blocker), str(repository_root))),
    }

    ordinary = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "--help"],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    development = subprocess.run(
        [
            sys.executable,
            "-m",
            "researchclaw.codex.cli",
            "execution",
            "run",
            str(project.root),
            "--input-manifest",
            "experiment/input_manifest.dev.json",
            "--development",
            "--confirm-development-run",
            "--json",
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ordinary.returncode == 0
    assert ordinary.stdout.startswith("usage: researchclaw-codex ")
    assert development.returncode == 2
    assert development.stdout == ""
    assert development.stderr == "error: numpy_unavailable\n"
    assert prior_result.read_bytes() == b'{"prior":true}\n'
    event = json.loads(
        (project.root / "evaluation/events.jsonl").read_text().splitlines()[-1]
    )
    assert event["type"] == "development_execution_failed"
    assert event["payload"] == {
        "input_manifest_path": "experiment/input_manifest.dev.json",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "error_category": "numpy_unavailable",
    }


@pytest.mark.parametrize(
    ("omitted_flag", "expected_flag"),
    [
        ("--input-manifest", "--input-manifest"),
        ("--development", "--development"),
        ("--confirm-development-run", "--confirm-development-run"),
    ],
)
def test_execution_run_cli_requires_explicit_development_intent(
    tmp_path, capsys, omitted_flag, expected_flag
):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", readiness="needs_input"
    )
    write_runnable_development_fixture(project)
    arguments = [
        "execution",
        "run",
        str(project.root),
        "--input-manifest",
        "experiment/input_manifest.dev.json",
        "--development",
        "--confirm-development-run",
        "--json",
    ]
    index = arguments.index(omitted_flag)
    del arguments[index : index + (2 if omitted_flag == "--input-manifest" else 1)]

    assert main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected_flag in captured.err
    assert not (project.root / "experiment/dev_results.json").exists()


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
    assert state.next_action == (
        "validate_experiment_package"
        if lineage_damage == "tampered-package-file"
        else "validate_stage"
    )
    assert not (project.root / "approvals/stage-12.json").exists()
