import json

from researchclaw.codex.cli import main


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
