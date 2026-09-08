import json

import pytest

from researchclaw.codex.cli import main
from tests.codex_native.m1.test_project import snapshot


def test_m1_cli_init_and_readonly_status(tmp_path, capsys):
    assert main(['m1', 'init', str(tmp_path), '--topic', 'fixture', '--profile', 'materials_ai', '--max-returns', '2', '--json']) == 0
    captured = capsys.readouterr()
    initial = json.loads(captured.out)
    assert captured.err == ''
    assert initial['schema_version'] == 1
    before = snapshot(tmp_path)
    assert main(['m1', 'status', str(tmp_path), '--json']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert json.loads(captured.out) == initial
    assert snapshot(tmp_path) == before
    assert main(['m1', 'status', str(tmp_path)]) == 0
    assert capsys.readouterr().out


def test_m1_cli_failure_is_stderr_exit_two(tmp_path, capsys):
    assert main(['m1', 'status', str(tmp_path), '--json']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'm1_' in captured.err


@pytest.mark.parametrize('args', [[], ['init'], ['status'], ['init', 'root', '--topic', 'fixture', '--max-returns', 'bad']])
def test_m1_cli_invalid_arguments(args, capsys):
    assert main(['m1', *args]) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err
