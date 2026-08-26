import json
import subprocess
import sys

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
