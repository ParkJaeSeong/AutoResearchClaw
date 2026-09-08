import importlib.util

import pytest

from researchclaw.core.m1 import store
from tests.codex_native.m1.test_project import initialize, snapshot


def api():
    assert importlib.util.find_spec('researchclaw.core.m1.packets') is not None, 'M1 packet implementation is missing'
    from researchclaw.core.m1.packets import prepare_node, register_outputs
    return prepare_node, register_outputs


def test_prepare_persists_packet_reuses_attempt_and_binds_config(tmp_path):
    initialize(tmp_path)
    prepare, _ = api()
    first = prepare(tmp_path, 'scope', command_id='prepare')
    packet = first['packet']
    assert packet['work_dir'] == f"m1/work/{packet['attempt_id']}"
    assert packet['input_binding']
    assert packet['allowed_outputs'] == ['scope/goal.md', 'scope/constraints.json']
    assert first['attempt']['input_refs'] == []
    assert first['attempt']['revision'] == 1
    assert (tmp_path / packet['work_dir']).is_dir()
    again = prepare(tmp_path, 'scope', command_id='prepare-alias')
    assert again['packet'] == packet
    assert len(again['receipt']['state']['attempts']) == 1
    head = store.read_head(tmp_path)
    assert prepare(tmp_path, 'scope', command_id='prepare') == first
    assert store.read_head(tmp_path) == head
    with pytest.raises(ValueError, match='m1_command_conflict'):
        prepare(tmp_path, 'questions', command_id='prepare')


def test_prepare_rejects_unknown_and_ineligible_nodes(tmp_path):
    initialize(tmp_path)
    prepare, _ = api()
    for node, error in [('unknown', 'm1_node_unknown'), ('questions', 'm1_node_not_eligible')]:
        with pytest.raises(ValueError, match=error):
            prepare(tmp_path, node, command_id=node)
    assert store.read_head(tmp_path)['state']['attempts'] == []


def test_resume_is_readonly_and_actionable(tmp_path, monkeypatch):
    initialize(tmp_path)
    prepare, _ = api()
    from researchclaw.core.m1.project import resume_project
    assert resume_project(tmp_path)['action'] == 'prepare_node'
    packet = prepare(tmp_path, 'scope', command_id='p')['packet']
    (tmp_path / '.researchclaw/project-transaction.lock').unlink()
    before = snapshot(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('read-only resume attempted fsync')
    monkeypatch.setattr(store.os, 'fsync', forbidden)
    result = resume_project(tmp_path)
    assert result['current_attempt']['id'] == packet['attempt_id']
    assert result['action'] == 'write_outputs'
    assert result['inputs']['configuration']['topic'] == 'fixture'
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('phase', ['before_head', 'after_head'])
def test_prepare_recovers_without_duplicate_attempts(tmp_path, monkeypatch, phase):
    initialize(tmp_path)
    prepare, _ = api()
    original = store._atomic_head
    def fail(base, commit_id):
        if phase == 'after_head':
            original(base, commit_id)
        raise OSError('simulated interruption')
    monkeypatch.setattr(store, '_atomic_head', fail)
    with pytest.raises(OSError, match='simulated interruption'):
        prepare(tmp_path, 'scope', command_id='p')
    assert len(store.read_head(tmp_path)['state']['attempts']) == (1 if phase == 'after_head' else 0)
    monkeypatch.setattr(store, '_atomic_head', original)
    result = prepare(tmp_path, 'scope', command_id='p')
    assert len(result['receipt']['state']['attempts']) == 1
    assert prepare(tmp_path, 'scope', command_id='p') == result


def test_prepare_requires_missing_inputs_and_binds_registered_id_and_hash(tmp_path):
    initialize(tmp_path)
    prepare, register = api()
    from tests.codex_native.m1.test_artifacts import draft
    packet = prepare(tmp_path, 'scope', command_id='p')['packet']
    result = register(tmp_path, packet_id=packet['id'], submission=draft(tmp_path, packet), command_id='r')
    head = result['receipt']
    state = head['state']
    # Fixture transition only: Task06 exposes no operation that bypasses the gate.
    state['current_node_id'] = 'questions'
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture_transition', state=state,
                        event={**store._VERSION, 'type': 'test_fixture_transition', 'payload': {}}, objects={})
    question = prepare(tmp_path, 'questions', command_id='q')['packet']
    assert {ref['id'] for ref in question['inputs']['objects']} == {ref['id'] for ref in result['artifacts']}
    head = store.read_head(tmp_path)
    head['state']['artifacts'][0]['id'] += '-changed'
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture_input_change', state=head['state'],
                        event={**store._VERSION, 'type': 'test_fixture_input_change', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_input_binding_changed'):
        prepare(tmp_path, 'questions', command_id='q-new')


def test_resume_reviews_and_budget_waits_are_readonly(tmp_path, monkeypatch):
    initialize(tmp_path)
    prepare, register = api()
    from researchclaw.core.m1.project import resume_project
    from tests.codex_native.m1.test_artifacts import draft
    packet = prepare(tmp_path, 'scope', command_id='p')['packet']
    for i in range(3):
        manifest = draft(tmp_path, packet, {'scope/goal.md': b'goal', 'scope/constraints.json': f'bad{i}'.encode()})
        register(tmp_path, packet_id=packet['id'], submission=manifest, command_id=f'r{i}')
    before = snapshot(tmp_path)
    result = resume_project(tmp_path)
    assert result['action'] == 'await_user'
    assert 'two draft corrections' in result['wait_reasons'][0]
    assert snapshot(tmp_path) == before


def test_unregistered_input_reference_cannot_become_packet_input(tmp_path):
    initialize(tmp_path)
    prepare, _ = api()
    head = store.read_head(tmp_path)
    head['state']['current_node_id'] = 'questions'
    head['state']['artifacts'] = [
        {'id': 'foreign-' + name, 'logical_path': 'scope/' + name, 'sha256': '0' * 64,
         'size': 12, 'producer_attempt_id': 'foreign'}
        for name in ('goal.md', 'constraints.json')]
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture_unregistered', state=head['state'],
                        event={**store._VERSION, 'type': 'test_fixture_unregistered', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_input_ref_invalid'):
        prepare(tmp_path, 'questions', command_id='q')


def test_prepare_does_not_reuse_obsolete_packet_version(tmp_path):
    initialize(tmp_path)
    prepare, _ = api()
    packet = prepare(tmp_path, 'scope', command_id='p')['packet']
    head = store.read_head(tmp_path)
    head['state']['packets'][packet['id']]['packet_version'] = 0
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture_old_version', state=head['state'],
                        event={**store._VERSION, 'type': 'test_fixture_old_version', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_input_binding_changed'):
        prepare(tmp_path, 'scope', command_id='new')
