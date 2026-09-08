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


def test_import_cli_and_inspect_never_expose_pending_initials(tmp_path, capsys):
    from tests.codex_native.research_graph.test_migration import source_fixture
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    args = ['research', 'import-m1', str(source), str(target), '--source-head', selected['id'],
            '--command-id', 'import', '--json']
    assert main(args) == 0
    raw = capsys.readouterr().out
    assert 'SECRET PENDING BODY' not in raw
    first = json.loads(raw)
    assert 'state' not in first and 'objects' not in first and 'events' not in first
    assert first['import']['issue_count'] == 6
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert main(['research', 'inspect', str(target), '--json']) == 0
    raw = capsys.readouterr().out
    summary = json.loads(raw)
    assert summary['import']['issue_status_counts'] == {'open': 6}
    assert summary['import']['source_head'] == selected['id']
    assert summary['import']['archive_read_only'] is True
    assert 'SECRET' not in raw and 'state' not in summary
