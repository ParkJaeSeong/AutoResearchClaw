def test_init_validate_five_stages_approve_resume_and_evaluate(tmp_path, capsys):
    from tests.codex_native.helpers import (
        run_cli,
        run_cli_json,
        write_valid_fixture_artifacts,
    )

    root = tmp_path / "demo"
    run_cli(
        "init",
        str(root),
        "--topic",
        "Formation energy",
        "--profile",
        "materials_ai",
        "--json",
    )
    capsys.readouterr()

    for stage_id in range(1, 6):
        packet = run_cli_json(capsys, "stage", "prepare", str(root), "--json")
        assert packet["stage_id"] == stage_id
        write_valid_fixture_artifacts(root, stage_id)
        report = run_cli_json(capsys, "stage", "validate", str(root), "--json")
        assert report["valid"] is True

    gate_status = run_cli_json(capsys, "status", str(root), "--json")
    assert gate_status["status"] == "awaiting_approval"
    run_cli(
        "approve",
        str(root),
        "--decision",
        "approve",
        "--note",
        "Corpus accepted",
        "--json",
    )
    capsys.readouterr()

    resumed = run_cli_json(capsys, "resume", str(root), "--json")
    assert resumed["current_stage"] == 6
    evaluation = run_cli_json(capsys, "evaluate", str(root), "--json")
    assert evaluation["stage_completion_rate"] == 5 / 23
    assert evaluation["external_llm_calls"] == 0
