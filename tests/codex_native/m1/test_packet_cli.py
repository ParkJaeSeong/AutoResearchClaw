import json
import os
from pathlib import Path
import subprocess

from tests.codex_native.m1.test_artifacts import draft


def cli(*args):
    env = {**os.environ, 'PATH': str(Path('.venv/bin').resolve()) + os.pathsep + os.environ['PATH']}
    return subprocess.run(['researchclaw-codex', 'm1', *map(str, args), '--json'], capture_output=True, text=True, env=env, timeout=20)


def test_cli_prepare_register_resume_and_replay(tmp_path):
    initialized = cli('init', tmp_path, '--topic', 'fixture')
    assert initialized.returncode == 0, initialized.stderr
    prepared = cli('node', 'prepare', tmp_path, '--node', 'scope', '--command-id', 'p')
    assert prepared.returncode == 0, prepared.stderr
    packet = json.loads(prepared.stdout)['packet']
    submission = draft(tmp_path, packet)
    manifest = tmp_path / 'submission.json'
    manifest.write_text(json.dumps(submission))
    args = ('node', 'register', tmp_path, '--packet', packet['id'], '--submission', manifest, '--command-id', 'r')
    registered = cli(*args)
    assert registered.returncode == 0, registered.stderr
    assert json.loads(registered.stdout)['status'] == 'review_pending'
    for ref in submission['files'].values():
        (tmp_path / ref['path']).unlink()
    assert cli(*args).stdout == registered.stdout
    resumed = cli('resume', tmp_path)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)['action'] == 'await_review'


def test_cli_invalid_content_persists_correction_and_reports_error(tmp_path):
    assert cli('init', tmp_path, '--topic', 'fixture').returncode == 0
    prepared = cli('node', 'prepare', tmp_path, '--node', 'scope', '--command-id', 'p')
    assert prepared.returncode == 0, prepared.stderr
    packet = json.loads(prepared.stdout)['packet']
    submission = draft(tmp_path, packet, {'scope/goal.md': b'goal', 'scope/constraints.json': b'bad'})
    manifest = tmp_path / 'submission.json'
    manifest.write_text(json.dumps(submission))
    result = cli('node', 'register', tmp_path, '--packet', packet['id'], '--submission', manifest, '--command-id', 'r')
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'm1_output_validation_failed' in result.stderr
    resumed = json.loads(cli('resume', tmp_path).stdout)
    assert resumed['action'] == 'correct_outputs'
    assert len(resumed['current_attempt']['validation_history']) == 1
