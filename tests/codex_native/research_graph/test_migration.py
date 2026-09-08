import importlib.util
import json
from uuid import UUID

import pytest

from researchclaw.core.m1 import store as legacy
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.contracts import validate_record
from tests.codex_native.m1.test_project import initialize


def api():
    assert importlib.util.find_spec('researchclaw.core.research_graph.migration'), 'explicit migration missing'
    from researchclaw.core.research_graph import migration
    return migration


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_mtime_ns,
            p.read_bytes() if p.is_file() else None) for p in root.rglob('*')}


def source_fixture(root):
    head = initialize(root)
    issues = [dict(id=f'old-{i}', question=f'Question {i}', raised_by='reviewer', severity='blocking',
                   impact='blocks hypothesis', resolution_condition='Check original',
                   target_refs=[], evidence_refs=[]) for i in range(6)]
    session = dict(id='r1', source_attempt_id='hypothesis-attempt-17', review_attempt_id='review-attempt-19',
        status='completed', content_origin='synthetic', input_refs=[],
        disclosed_initials=[dict(open_issues=issues)], disclosed_responses=[], disclosed_final_positions=[],
        initials={}, responses={}, final_positions=[])
    state = {**head['state'], 'content_origin': 'synthetic', 'sessions': {'r1': session},
             'attempts': [dict(id='hypothesis-attempt-17', node_id='hypothesize'),
                          dict(id='review-attempt-19', node_id='review')]}
    head = legacy.commit_record(root, expected_head=head['id'], command_id='r1', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={'evidence.txt': b'original'})
    state = {**head['state'], 'sessions': {**head['state']['sessions'], 'r2': {
        **session, 'id': 'r2', 'source_attempt_id': 'hypothesis-attempt-20',
        'review_attempt_id': 'review-attempt-21', 'disclosed_initials': [], 'status': 'collecting_initials',
        'initials': {'private': {'open_issues': [{**issues[0], 'question': 'SECRET PENDING BODY'}]}}}}}
    selected = legacy.commit_record(root, expected_head=head['id'], command_id='r2', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={'pending.txt': b'SECRET PENDING BODY'})
    return selected


def test_old_six_issues_survive_new_round_and_original_is_unchanged(tmp_path):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    before = snapshot(source)
    result = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    assert snapshot(source) == before
    state = result['state']
    assert len(state['issues']) == 6
    assert not state.get('sessions') and not state.get('issue_events')
    assert {v['source_status'] for v in state['imported_issue_states'].values()} == {'open'}
    for issue in state['issues'].values():
        assert not validate_record('Issue', issue)
        assert issue['owner_assignment_id'] is None
        UUID(issue['origin']['attempt'])
    archive = state['source_archive']
    assert archive['head_id'] == selected['id']
    assert archive['sessions']['r2']['read_only'] is True
    assert archive['id_map']['attempts']['review-attempt-19'] == next(iter(state['issues'].values()))['origin']['attempt']
    assert 'SECRET' not in json.dumps(state)
    for digest in selected['objects']:
        assert (target / '.researchclaw/research_graph/objects' / digest).read_bytes() == (source / '.researchclaw/m1/objects' / digest).read_bytes()
    assert migration.import_m1(source, target, source_head=selected['id'], command_id='import') == result


def test_selected_history_excludes_later_commits_and_objects_replay_after_both_advance(tmp_path):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    later = legacy.commit_record(source, expected_head=selected['id'], command_id='later', state=selected['state'],
        event={**legacy._VERSION, 'type': 'later', 'payload': {}}, objects={'later.txt': b'LATER PRIVATE'})
    first = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    archive = first['state']['source_archive']
    assert later['id'] not in archive['commits']
    assert legacy._hash(b'LATER PRIVATE') not in first['objects']
    for commit_id, digest in archive['commits'].items():
        assert (target / '.researchclaw/research_graph/objects' / digest).read_bytes() == (source / '.researchclaw/m1/commits' / commit_id / 'record.json').read_bytes()
    advanced = store.commit_record(target, expected_head=first['id'], command_id='advance', state=first['state'],
        event={**store._VERSION, 'type': 'advance', 'payload': {}}, objects={})
    before = snapshot(target)
    assert migration.import_m1(source, target, source_head=selected['id'], command_id='import') == first
    assert snapshot(target) == before
    assert store.read_head(target) == advanced
    with pytest.raises(ValueError, match='conflict'):
        migration.import_m1(source, target, source_head=later['id'], command_id='import')


@pytest.mark.parametrize('kind', ['equal', 'nested_target', 'nested_source', 'nonempty', 'unreachable', 'corrupt', 'symlink'])
def test_unsafe_source_target_rejected_without_changes(tmp_path, kind):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    head_id = selected['id']
    if kind == 'equal': target = source
    if kind == 'nested_target': target = source / 'nested'
    if kind == 'nested_source': target = tmp_path
    if kind == 'nonempty':
        target.mkdir()
        (target / 'keep').write_text('keep')
    if kind == 'unreachable': head_id = '0' * 64
    if kind == 'corrupt':
        (source / '.researchclaw/m1/objects' / next(iter(selected['objects']))).write_bytes(b'corrupt')
    if kind == 'symlink':
        linked = tmp_path / 'linked'
        linked.symlink_to(source, target_is_directory=True)
        source = linked
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        migration.import_m1(source, target, source_head=head_id, command_id='import')
    assert snapshot(tmp_path) == before


def test_copy_failure_never_publishes_complete_head(tmp_path, monkeypatch):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    before = snapshot(source)
    original = store._write_file
    def fail(path, data):
        if path.parent.name == 'objects': raise OSError('interrupted copy')
        return original(path, data)
    monkeypatch.setattr(store, '_write_file', fail)
    with pytest.raises(OSError, match='interrupted copy'):
        migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    assert not (target / '.researchclaw/research_graph/HEAD.json').exists()
    assert snapshot(source) == before


def test_legacy_research_origin_and_canonical_resolution_preserved(tmp_path):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    state = selected['state']
    state['content_origin'] = 'research'
    session = state['sessions']['r1']
    session['content_origin'] = 'research'
    session['disclosed_final_positions'] = [{'assignment_id': 'reviewer',
        'issue_dispositions': [{'issue_id': 'old-0', 'status': 'resolved'}]}]
    session['final_positions'] = session['disclosed_final_positions']
    # Equal local IDs in another disclosed council must remain distinct.
    state['sessions']['r2'] = {**session, 'id': 'r2', 'review_attempt_id': 'review-attempt-21',
                              'source_attempt_id': 'hypothesis-attempt-20'}
    selected = legacy.commit_record(source, expected_head=selected['id'], command_id='disclosed', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    result = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    state = result['state']
    assert state['content_origin'] == 'real'
    assert state['source_archive']['source_content_origin'] == 'research'
    assert len(state['issues']) == 12
    assert all(issue['content_origin'] == 'real' for issue in state['issues'].values())
    assert sum(s['source_status'] == 'resolved' for s in state['imported_issue_states'].values()) == 2
    assert state['issue_events'] == []
    assert all(i['owner_assignment_id'] is None for i in state['issues'].values())


@pytest.mark.parametrize('field,value', [('sessions', None), ('sessions', []), ('attempts', [None]),
    ('sessions', {'r1': None}), ('content_origin', 'unknown')])
def test_malformed_legacy_state_rejected_as_validation_error(tmp_path, field, value):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    head = source_fixture(source)
    selected = legacy.commit_record(source, expected_head=head['id'], command_id='malformed',
        state={**head['state'], field: value}, event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='import_source_invalid'):
        migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    assert not target.exists()


def test_same_command_other_source_conflicts_and_unknown_pending_origin_rejected(tmp_path):
    import shutil
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    first = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    other = tmp_path / 'copied-source'
    shutil.copytree(source, other)
    with pytest.raises(ValueError, match='command_conflict'):
        migration.import_m1(other, target, source_head=selected['id'], command_id='import')
    assert store.read_head(target) == first
    state = selected['state']
    state['sessions']['r2']['content_origin'] = 'unknown'
    changed = legacy.commit_record(source, expected_head=selected['id'], command_id='bad-origin', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='import_source_invalid'):
        migration.import_m1(source, tmp_path / 'rejected', source_head=changed['id'], command_id='new-import')


def test_missing_disclosed_issue_field_rejected_without_target(tmp_path):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    state = selected['state']
    del state['sessions']['r1']['disclosed_initials'][0]['open_issues'][0]['question']
    changed = legacy.commit_record(source, expected_head=selected['id'], command_id='bad-issue', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='import_source_invalid'):
        migration.import_m1(source, target, source_head=changed['id'], command_id='import')
    assert not target.exists()


def test_targets_resolve_only_exact_session_artifact_and_revision(tmp_path):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    old_bytes = legacy._canonical({'hypotheses': [{'id': 'H1', 'revision': 1, 'statement': 'old'}]})
    new_bytes = legacy._canonical({'hypotheses': [{'id': 'H1', 'revision': 2, 'statement': 'new'}]})
    refs = [dict(id=name, sha256=legacy._hash(data), size=len(data), logical_path='hypotheses/hypotheses.json')
            for name, data in [('hypotheses-old', old_bytes), ('hypotheses-new', new_bytes)]]
    state = selected['state']
    state['artifacts'] = refs
    state['sessions']['r1']['input_refs'] = [refs[0]]
    issue = state['sessions']['r1']['disclosed_initials'][0]['open_issues'][0]
    issue['target_refs'] = [{'id': 'H1', 'revision': 1}, {'id': 'H1', 'revision': 2}]
    selected = legacy.commit_record(source, expected_head=selected['id'], command_id='targets', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}},
        objects={'old.json': old_bytes, 'new.json': new_bytes})
    imported = migration.import_m1(source, target, source_head=selected['id'], command_id='import')['state']
    issue_id = imported['source_archive']['id_map']['issues']['r1']['old-0']
    expected = dict(project_id=imported['source_archive']['project_id'], head_id=selected['id'],
                    artifact_id='hypotheses-old', sha256=legacy._hash(old_bytes))
    assert imported['issues'][issue_id]['target_refs'] == [expected]
    metadata = imported['imported_issue_states'][issue_id]
    assert metadata['original_target_refs'] == issue['target_refs']
    assert metadata['target_mappings'] == [{'original_target_ref': {'id': 'H1', 'revision': 1},
        'snapshot_ref': expected, 'source_json_pointer': '/hypotheses/0'}]
    assert len(metadata['limitations']) == 1
    assert 'revision' in metadata['limitations'][0]


@pytest.mark.parametrize('field', ['disclosed_initials', 'disclosed_responses', 'disclosed_final_positions'])
@pytest.mark.parametrize('value', ['malformed', None, {}, [None], [{}]])
def test_malformed_disclosed_round_rejected_without_source_change(tmp_path, field, value):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    head = source_fixture(source)
    state = head['state']
    state['sessions']['r1'][field] = value
    selected = legacy.commit_record(source, expected_head=head['id'], command_id='bad-disclosure',
        state=state, event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    before = snapshot(source)
    with pytest.raises(ValueError, match='import_source_invalid'):
        migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    assert not target.exists()
    assert snapshot(source) == before


@pytest.mark.parametrize('field,value', [
    ('disclosed_initials', [{'open_issues': {}}]),
    ('disclosed_initials', [{'open_issues': [None]}]),
    ('disclosed_responses', [{'responses': [], 'new_issues': {}}]),
    ('disclosed_responses', [{'responses': [None], 'new_issues': []}]),
    ('disclosed_responses', [{'responses': [{}], 'new_issues': []}]),
    ('disclosed_final_positions', [{'assignment_id': 'reviewer', 'issue_dispositions': {}}]),
    ('disclosed_final_positions', [{'assignment_id': 'reviewer', 'issue_dispositions': [None]}]),
    ('disclosed_final_positions', [{'assignment_id': 'reviewer', 'issue_dispositions': [{'issue_id': 'old-0', 'status': 'invalid'}]}]),
])
def test_malformed_disclosed_nested_members_rejected(tmp_path, field, value):
    migration = api()
    source, target = tmp_path / 'source', tmp_path / 'target'
    head = source_fixture(source)
    state = head['state']
    state['sessions']['r1'][field] = value
    selected = legacy.commit_record(source, expected_head=head['id'], command_id='bad-disclosure',
        state=state, event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={})
    before = snapshot(source)
    with pytest.raises(ValueError, match='import_source_invalid'):
        migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    assert not target.exists()
    assert snapshot(source) == before
