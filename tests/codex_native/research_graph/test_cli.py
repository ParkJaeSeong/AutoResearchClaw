import json
from researchclaw.codex.cli import main


def test_init_inspect_replay_and_generic_error(tmp_path, capsys):
    args = ['research', 'init', str(tmp_path), '--topic', 'A topic', '--content-origin', 'synthetic', '--json']
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert main(['research', 'inspect', str(tmp_path), '--json']) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['head_id'] == first['id']
    assert 'state' not in summary and 'events' not in summary
    assert main(['research', 'inspect', str(tmp_path / 'private-name'), '--json']) == 2
    error = capsys.readouterr().err
    assert 'private-name' not in error
    assert json.loads(error)['error']['code'] == 'research_graph_request_failed'
