import hashlib
import importlib.util
import json

import pytest

from researchclaw.core.m1 import store
from tests.codex_native.m1.test_packets import api
from tests.codex_native.m1.test_project import initialize, snapshot


def validator():
    assert importlib.util.find_spec('researchclaw.core.m1.artifacts') is not None, 'M1 output validation is missing'
    from researchclaw.core.m1.artifacts import validate_outputs
    return validate_outputs


def draft(root, packet, files=None):
    files = files if files is not None else {'scope/goal.md': b'# Objective\n', 'scope/constraints.json': b'{}'}
    manifest = {'schema_version': 1, 'files': {}}
    for logical, data in files.items():
        path = f"{packet['work_dir']}/{logical}"
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest['files'][logical] = {'path': path, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    return manifest


def setup(root):
    initialize(root)
    prepare, register = api()
    packet = prepare(root, 'scope', command_id='p')['packet']
    return packet, prepare, register


def test_undeclared_output_is_rejected():
    issues = validator()({'schema_version': 1, 'node_id': 'scope', 'allowed_outputs': ['scope/goal.md']}, {'../escape.txt': b'x'})
    assert any(issue['code'] == 'm1_undeclared_output' for issue in issues)


@pytest.mark.parametrize('files,code', [({}, 'm1_required_output_missing'), ({'scope/goal.md': b'\xff', 'scope/constraints.json': b'{}'}, 'm1_output_utf8_invalid'), ({'scope/goal.md': b'ok', 'scope/constraints.json': b'{bad'}, 'm1_output_format_invalid')])
def test_required_files_and_content_formats(files, code):
    issues = validator()({'schema_version': 1, 'node_id': 'scope', 'allowed_outputs': ['scope/goal.md', 'scope/constraints.json']}, files)
    assert any(issue['code'] == code for issue in issues)


def test_unknown_node_and_unsafe_yaml_rejected():
    assert validator()({'node_id': 'unknown', 'allowed_outputs': []}, {})[0]['code'] == 'm1_node_unknown'
    issues = validator()({'node_id': 'search', 'allowed_outputs': ['literature/search_plan.yaml']}, {'literature/search_plan.yaml': b'!!python/object/apply:os.system ["touch /tmp/never"]'})
    assert issues[0]['code'] == 'm1_output_format_invalid'


def test_registration_atomic_review_pending_and_replay_after_draft_removal(tmp_path):
    packet, prepare, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    result = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    assert result['status'] == 'review_pending'
    assert len(result['artifacts']) == 2
    state = result['receipt']['state']
    assert state['current_node_id'] == 'scope'
    assert state['attempts'][-1]['status'] == 'review_pending'
    assert state['attempts'][-1]['structural_validation'] == 'passed'
    assert state['attempts'][-1]['scientific_validation'] == 'not_performed'
    for item in manifest['files'].values():
        (tmp_path / item['path']).unlink()
    with pytest.raises(ValueError, match='m1_node_waiting'):
        prepare(tmp_path, 'scope', command_id='p-next')
    head = store.read_head(tmp_path)
    later = store.commit_record(tmp_path, expected_head=head['id'], command_id='later', state={**head['state'], 'marker': 1}, event={**store._VERSION, 'type': 'test_advance', 'payload': {}}, objects={})
    assert register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r') == result
    assert store.read_head(tmp_path) == later
    manifest['files']['scope/goal.md']['size'] += 1
    with pytest.raises(ValueError, match='m1_command_conflict'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')


@pytest.mark.parametrize('path', ['/etc/passwd', '../outside', 'm1/work/other/scope/goal.md', '.researchclaw/m1/HEAD.json'])
def test_unsafe_manifest_rejected_without_read_or_budget(tmp_path, path):
    packet, _, register = setup(tmp_path)
    manifest = {'schema_version': 1, 'files': {'scope/goal.md': {'path': path, 'sha256': '0' * 64, 'size': 0}}}
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_submission_invalid'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='bad')
    assert snapshot(tmp_path) == before


def test_symlink_substitution_and_changed_bytes_rejected(tmp_path):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    target = tmp_path / manifest['files']['scope/goal.md']['path']
    target.write_bytes(b'changed')
    with pytest.raises(ValueError, match='m1_submission_content_changed'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    target.unlink()
    target.symlink_to(tmp_path / '.researchclaw/m1/HEAD.json')
    with pytest.raises(ValueError, match='m1_submission_path_invalid'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')


def test_old_packet_and_changed_binding_rejected(tmp_path):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    head = store.read_head(tmp_path)
    state = {**head['state'], 'topic': 'changed'}
    store.commit_record(tmp_path, expected_head=head['id'], command_id='change', state=state, event={**store._VERSION, 'type': 'changed', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_input_binding_changed'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    head = store.read_head(tmp_path)
    state['current_node_id'] = 'questions'
    store.commit_record(tmp_path, expected_head=head['id'], command_id='advance', state=state, event={**store._VERSION, 'type': 'advanced', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_packet_stale'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r2')


def test_three_invalid_submissions_exhaust_budget_duplicates_do_not(tmp_path):
    packet, prepare, register = setup(tmp_path)
    for index in range(3):
        manifest = draft(tmp_path, packet, {'scope/goal.md': b'ok', 'scope/constraints.json': f'bad-{index}'.encode()})
        result = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id=f'r{index}')
        assert result['status'] == ('awaiting_user' if index == 2 else 'draft_invalid')
        duplicate = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id=f'alias{index}')
        assert len(duplicate['receipt']['state']['attempts'][-1]['validation_history']) == index + 1
    with pytest.raises(ValueError, match='m1_node_waiting'):
        prepare(tmp_path, 'scope', command_id='reset-budget')
    manifest = draft(tmp_path, packet)
    with pytest.raises(ValueError, match='m1_draft_budget_exhausted'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='fourth')
    assert store.read_head(tmp_path)['state']['returns_used'] == 0


@pytest.mark.parametrize('phase', ['before_head', 'after_head'])
def test_register_recovers_from_publication_failure(tmp_path, monkeypatch, phase):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    original = store._atomic_head
    def fail(base, commit_id):
        if phase == 'after_head':
            original(base, commit_id)
        raise OSError('simulated interruption')
    monkeypatch.setattr(store, '_atomic_head', fail)
    with pytest.raises(OSError, match='simulated interruption'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    head = store.read_head(tmp_path)
    assert head['state']['attempts'][-1]['status'] == ('review_pending' if phase == 'after_head' else 'prepared')
    if phase == 'after_head':
        for ref in manifest['files'].values():
            (tmp_path / ref['path']).unlink()
    monkeypatch.setattr(store, '_atomic_head', original)
    result = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    assert result['status'] == 'review_pending'
    assert len(result['receipt']['state']['attempts'][-1]['validation_history']) == 1
    assert len(result['receipt']['events']) == 3


def test_commit_uses_validated_snapshot_even_when_draft_replaced(tmp_path, monkeypatch):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    import researchclaw.core.m1.packets as packets
    original = packets.validate_outputs
    def validate_then_replace(packet, files):
        result = original(packet, files)
        for ref in manifest['files'].values():
            (tmp_path / ref['path']).write_bytes(b'replaced after validation')
        return result
    monkeypatch.setattr(packets, 'validate_outputs', validate_then_replace)
    result = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    for ref in result['artifacts']:
        data = (tmp_path / '.researchclaw/m1/objects' / ref['sha256']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == manifest['files'][ref['logical_path']]['sha256']
        assert data != b'replaced after validation'


def test_parent_symlink_substitution_rejected(tmp_path):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    parent = tmp_path / packet['work_dir'] / 'scope'
    elsewhere = tmp_path / 'other'
    parent.rename(elsewhere)
    parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match='m1_submission_path_invalid'):
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')


def test_success_duplicate_new_command_reuses_artifacts_after_deletion(tmp_path):
    packet, _, register = setup(tmp_path)
    manifest = draft(tmp_path, packet)
    first = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='r')
    for ref in manifest['files'].values():
        (tmp_path / ref['path']).unlink()
    alias = register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='alias')
    assert alias['artifacts'] == first['artifacts']
    assert len(alias['receipt']['state']['attempts'][-1]['validation_history']) == 1
    assert register(tmp_path, packet_id=packet['id'], submission=manifest, command_id='alias') == alias


@pytest.mark.parametrize('node,path,data', [('collect', 'literature/candidates.jsonl', b'{"ok":1}\n{"bad"'), ('scope', 'scope/constraints.json', b'{"x":1,"x":2}'), ('scope', 'scope/constraints.json', b'{"x":NaN}')])
def test_strict_json_and_jsonl_formats(node, path, data):
    from researchclaw.core.m1.roles import describe_roles
    packet = {'node_id': node, 'allowed_outputs': describe_roles(node)['outputs']}
    files = {name: b'{}' for name in packet['allowed_outputs']}
    files[path] = data
    assert any(issue['code'] == 'm1_output_format_invalid' for issue in validator()(packet, files))
