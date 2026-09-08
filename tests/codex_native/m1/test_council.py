"""Synthetic checkpoint tests: no actual role execution is claimed here."""
from copy import deepcopy
import importlib
import importlib.util
import json

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
from tests.codex_native.m1.helpers import checkpoint
from tests.codex_native.m1.test_assignments import assignments
from tests.codex_native.m1.test_hypotheses import prepare_case, register, envelope, candidate


def api():
    name = 'researchclaw.core.m1.council'
    assert importlib.util.find_spec(name) is not None, 'M1 independent council is missing'
    return importlib.import_module(name)


def prepared(root):
    packet = prepare_case(root)
    register(root, packet, envelope(candidate()))
    return api().prepare_council(root, attempt_id=packet['attempt_id'], assignments=assignments(),
                                 command_id='prepare-council')


def initial(session, reviewer_id='A1', **updates):
    assignment_id = reviewer_id
    assignment = next(a for a in session['assignments'] if a['id'] == assignment_id)
    return {'schema_version': 1, 'id': 'I-' + assignment_id, 'session_id': session['id'],
            'assignment_id': assignment_id, 'role_id': assignment['role_id'],
            'host_task_id': assignment['host_task_id'], 'input_binding': session['input_binding'],
            'rationale': ['Independent reasoning for ' + assignment_id],
            'evidence_refs': [session['input_refs'][0]['id']], 'open_issues': [], **updates}


def submit(root, session, assignment_id='A1', command_id=None, **updates):
    return api().register_initial(root, session_id=session['id'], assignment_id=assignment_id,
                                  payload=initial(session, assignment_id, **updates),
                                  command_id=command_id or 'submit-' + assignment_id)


def test_initial_packet_does_not_disclose_another_initial():
    session = {'id': 'S1', 'input_binding': 'a' * 64,
               'assignments': [{'id': 'A1', 'role_id': 'domain'},
                               {'id': 'A2', 'role_id': 'methodology'},
                               {'id': 'A3', 'role_id': 'critical_reproducibility'}],
               'initials': {'A1': {'rationale': ['private initial']}},
               'responses': [], 'final_positions': [], 'status': 'collecting_initials'}
    packet = api().reviewer_packet(session, 'A2')
    assert packet['disclosed_initials'] == []
    assert packet['phase'] == 'initial'
    assert 'private initial' not in json.dumps(packet)


def test_prepare_binds_registered_inputs_and_preserves_hypothesis_gate(tmp_path):
    result = prepared(tmp_path)
    session = result['session']
    state = store.read_head(tmp_path)['state']
    assert state['current_node_id'] == 'review'
    assert state['attempts'][-2]['status'] == 'review_pending'
    assert state['attempts'][-1]['node_id'] == 'review'
    assert state['attempts'][-1]['source_attempt_id'] == session['source_attempt_id']
    assert state['attempts'][-1]['scientific_validation'] == 'not_performed'
    assert session['hypothesis_refs'] == [{'id': 'H1', 'revision': 1}]
    assert session['approval_id'] == state['approvals'][-1]['id']
    packets = [api().reviewer_packet(session, a['id']) for a in session['assignments']]
    assert all(p['allowed_evidence'] == packets[0]['allowed_evidence'] for p in packets)
    assert all(p['input_binding'] == session['input_binding'] for p in packets)
    assert all(p['disclosed_initials'] == [] for p in packets)
    assert packets[0]['allowed_evidence']
    assert session['content_origin'] == 'synthetic'


def test_all_three_initials_disclose_one_frozen_snapshot_and_reopen(tmp_path):
    session = prepared(tmp_path)['session']
    for assignment_id in ('A2', 'A1'):
        result = submit(tmp_path, session, assignment_id)
        stored = store.read_head(tmp_path)['state']['sessions'][session['id']]
        assert api().reviewer_packet(stored, 'A3')['disclosed_initials'] == []
        assert 'Independent reasoning' not in json.dumps(result)
    issue = {'id': 'issue-A3', 'raised_by': 'A3', 'target_refs': [{'id': 'H1', 'revision': 1}],
             'evidence_refs': [], 'question': 'Is abstract evidence sufficient?', 'impact': 'Inference is limited.',
             'severity': 'blocking', 'resolution_condition': 'Inspect full source evidence.'}
    submit(tmp_path, session, 'A3', open_issues=[issue])
    stored = store.read_head(tmp_path)['state']['sessions'][session['id']]
    packets = [api().reviewer_packet(stored, a) for a in ('A1', 'A2', 'A3')]
    assert all(p['phase'] == 'response' for p in packets)
    disclosed = packets[0]['disclosed_initials']
    assert [p['assignment_id'] for p in disclosed] == ['A1', 'A2', 'A3']
    assert all(p['disclosed_initials'] == disclosed for p in packets)
    assert disclosed[-1]['open_issues'] == [{**issue, 'session_id': session['id']}]
    assert all(p['provenance_status'] == 'declared_only' for p in disclosed)
    packets[0]['disclosed_initials'][0]['rationale'].append('mutation')
    assert 'mutation' not in api().reviewer_packet(stored, 'A2')['disclosed_initials'][0]['rationale']
    with pytest.raises(ValueError, match='m1_initial_conflict|m1_council_phase'):
        submit(tmp_path, session, 'A1', command_id='changed', rationale=['Changed after disclosure'])


@pytest.mark.parametrize('updates', [
    {'role_id': 'methodology'}, {'assignment_id': 'A2'}, {'host_task_id': 'other-host'},
    {'input_binding': 'b' * 64}, {'session_id': 'other'}, {'rationale': []},
    {'open_issues': [' ']}, {'evidence_refs': ['unknown']}, {'provenance_status': 'host_verified'},
])
def test_initial_contract_rejects_misbinding_and_unregistered_evidence(tmp_path, updates):
    session = prepared(tmp_path)['session']
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_initial'):
        api().register_initial(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=initial(session, **updates), command_id='invalid')
    assert store.read_head(tmp_path)['id'] == before


def test_durable_command_and_submission_replays_do_not_duplicate(tmp_path):
    result = prepared(tmp_path)
    session = result['session']
    first = submit(tmp_path, session)
    submit(tmp_path, session, 'A2')
    assert submit(tmp_path, session) == first
    duplicate = submit(tmp_path, session, command_id='alias')
    assert duplicate['initial_id'] == 'I-A1'
    assert len(store.read_head(tmp_path)['state']['sessions'][session['id']]['initials']) == 2
    with pytest.raises(ValueError, match='m1_command_conflict'):
        submit(tmp_path, session, rationale=['Different request'])
    replay = api().prepare_council(tmp_path, attempt_id=session['source_attempt_id'], assignments=assignments(),
                                   command_id='prepare-council')
    assert replay == result
    with pytest.raises(ValueError, match='m1_council_exists'):
        api().prepare_council(tmp_path, attempt_id=session['source_attempt_id'], assignments=assignments(), command_id='new')


@pytest.mark.parametrize('path', ['knowledge/extractions.jsonl', 'knowledge/synthesis.json',
                                  'hypotheses/hypotheses.json', 'scope/constraints.json'])
def test_new_registered_evidence_or_hypothesis_invalidates_session(tmp_path, path):
    session = prepared(tmp_path)['session']
    checkpoint(tmp_path, files={path: b'{}'})
    with pytest.raises(ValueError, match='m1_council_input_changed|m1_corpus'):
        submit(tmp_path, session)


def test_revoked_or_replaced_approval_invalidates_session(tmp_path):
    session = prepared(tmp_path)['session']
    corpus = current_corpus(tmp_path)
    for decision in ('reject', 'approve'):
        record_corpus_approval(tmp_path, corpus_binding=corpus['corpus_binding'], decision=decision,
                               note='Synthetic changed declaration', command_id='decision-' + decision)
        with pytest.raises(ValueError, match='m1_council_input_changed|m1_corpus_approval_required'):
            submit(tmp_path, session)


def test_failed_role_replacement_preserves_history_and_rejects_late_old_output(tmp_path):
    session = prepared(tmp_path)['session']
    submit(tmp_path, session)
    replacement = {'id': 'A4', 'role_id': 'methodology', 'host_task_id': 'host-4'}
    replaced = api().replace_assignment(tmp_path, session_id=session['id'], assignment_id='A2',
        replacement=replacement, reason='Native role failed before submitting.', command_id='replace')
    with pytest.raises(ValueError, match='m1_assignment_inactive'):
        submit(tmp_path, session, 'A2')
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    assert current['assignment_history'][0]['assignment']['id'] == 'A2'
    assert current['assignment_history'][0]['reason'] == 'Native role failed before submitting.'
    assert set(current['initials']) == {'A1'}
    assert api().reviewer_packet(current, 'A4')['disclosed_initials'] == []
    assert api().replace_assignment(tmp_path, session_id=session['id'], assignment_id='A2',
        replacement=replacement, reason='Native role failed before submitting.', command_id='replace') == replaced
    submit(tmp_path, current, 'A4')
    submit(tmp_path, current, 'A3')
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    assert [p['assignment_id'] for p in current['disclosed_initials']] == ['A1', 'A3', 'A4']
    with pytest.raises(ValueError, match='m1_council_phase'):
        api().replace_assignment(tmp_path, session_id=session['id'], assignment_id='A3',
            replacement={'id': 'A5', 'role_id': 'critical_reproducibility', 'host_task_id': 'host-5'},
            reason='Too late after disclosure', command_id='late-replace')


def test_submitted_role_can_be_replaced_before_disclosure_with_initial_retained_in_history(tmp_path):
    session = prepared(tmp_path)['session']
    submit(tmp_path, session)
    api().replace_assignment(tmp_path, session_id=session['id'], assignment_id='A1',
        replacement={'id': 'A4', 'role_id': 'domain', 'host_task_id': 'host-4'},
        reason='Role failed after initial; cannot continue', command_id='replace')
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    assert current['initials'] == {}
    assert current['assignment_history'][0]['initial']['id'] == 'I-A1'
    with pytest.raises(ValueError, match='m1_assignment_inactive'):
        submit(tmp_path, session, command_id='late')


def test_resume_reports_current_council_collection_phase(tmp_path):
    from researchclaw.core.m1.project import resume_project
    session = prepared(tmp_path)['session']
    result = resume_project(tmp_path)
    assert result['current_node_id'] == 'review'
    assert result['status'] == 'collecting_initials'
    assert result['action'] == 'collect_initials'
    assert result['session_id'] == session['id']
    for assignment_id in ('A1', 'A2', 'A3'):
        submit(tmp_path, session, assignment_id)
    assert resume_project(tmp_path)['action'] == 'collect_responses'


def test_cli_packet_status_and_replace_do_not_leak_private_initials(tmp_path, capsys):
    from researchclaw.codex.cli import main
    root = tmp_path / 'project'
    packet = prepare_case(root)
    register(root, packet, envelope(candidate()))
    assignments_file = tmp_path / 'assignments.json'
    assignments_file.write_text(json.dumps(assignments()))
    assert main(['m1', 'council', 'prepare', str(root), '--attempt', packet['attempt_id'],
        '--assignments', str(assignments_file), '--command-id', 'cli-prepare', '--json']) == 0
    captured = capsys.readouterr()
    assert not captured.err
    session = json.loads(captured.out)['session']
    payload_file = tmp_path / 'initial.json'
    payload_file.write_text(json.dumps(initial(session)))
    assert main(['m1', 'council', 'initial', str(root), '--session', session['id'], '--assignment', 'A1',
        '--submission', str(payload_file), '--command-id', 'cli-initial', '--json']) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert 'Independent reasoning' not in captured.out
    for args in (['m1', 'council', 'packet', str(root), '--session', session['id'], '--assignment', 'A2'],
                 ['m1', 'status', str(root)], ['m1', 'resume', str(root)]):
        assert main([*args, '--json']) == 0
        captured = capsys.readouterr()
        json.loads(captured.out)
        assert not captured.err
        assert 'Independent reasoning' not in captured.out
    replacement_file = tmp_path / 'replacement.json'
    replacement_file.write_text(json.dumps({'id': 'A4', 'role_id': 'methodology', 'host_task_id': 'host-4'}))
    assert main(['m1', 'council', 'replace', str(root), '--session', session['id'], '--assignment', 'A2',
        '--replacement', str(replacement_file), '--reason', 'Failed role', '--command-id', 'cli-replace', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['assignment']['id'] == 'A4'
    before = store.read_head(root)['id']
    assert main(['m1', 'council', 'packet', str(root), '--session', session['id'], '--assignment', 'A2', '--json']) == 2
    captured = capsys.readouterr()
    assert not captured.out and 'm1_assignment_inactive' in captured.err
    assert store.read_head(root)['id'] == before


def test_prepare_rejects_evidence_newer_than_hypothesis_producer(tmp_path):
    packet = prepare_case(tmp_path)
    register(tmp_path, packet, envelope(candidate()))
    checkpoint(tmp_path, files={'knowledge/extractions.jsonl': b'{}'})
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_council_input_changed'):
        api().prepare_council(tmp_path, attempt_id=packet['attempt_id'], assignments=assignments(), command_id='prepare')
    assert store.read_head(tmp_path)['id'] == before


def test_known_author_host_cannot_be_reviewer_under_another_assignment_id(tmp_path):
    packet = prepare_case(tmp_path)
    register(tmp_path, packet, envelope(candidate(author_host_task_id='host-1')))
    with pytest.raises(ValueError, match='m1_assignment_self_review'):
        api().prepare_council(tmp_path, attempt_id=packet['attempt_id'], assignments=assignments(), command_id='prepare')


@pytest.mark.parametrize('updates', [
    {'raised_by': 'A2'}, {'target_refs': [{'id': 'H1', 'revision': 2}]},
    {'target_refs': [{'id': 'H1', 'revision': True}]}, {'evidence_refs': ['not-bound']},
    {'question': ' '}, {'severity': 'none'}, {'related_issue_ids': ['hidden-other-issue']},
])
def test_structured_initial_issues_preserve_identity_and_validate_scope(tmp_path, updates):
    session = prepared(tmp_path)['session']
    issue = {'id': 'issue-A1', 'raised_by': 'A1', 'target_refs': [{'id': 'H1', 'revision': 1}],
             'evidence_refs': [], 'question': 'Is evidence sufficient?', 'impact': 'Uncertain inference',
             'severity': 'major', 'resolution_condition': 'Retrieve direct evidence', **updates}
    with pytest.raises(ValueError, match='m1_initial_issue_invalid'):
        submit(tmp_path, session, open_issues=[issue])


def test_replay_after_visible_publication_failure_restores_durability(tmp_path, monkeypatch):
    session = prepared(tmp_path)['session']
    original = store._sync_publication
    def fail_once(base):
        raise OSError('synthetic fsync interruption after publication')
    monkeypatch.setattr(store, '_sync_publication', fail_once)
    with pytest.raises(OSError, match='synthetic fsync'):
        submit(tmp_path, session)
    monkeypatch.setattr(store, '_sync_publication', original)
    head = store.read_head(tmp_path)
    result = submit(tmp_path, session)
    assert result['receipt']['id'] == head['id']
    assert len(store.read_head(tmp_path)['state']['sessions'][session['id']]['initials']) == 1


def test_corpus_cli_nested_receipt_also_hides_pending_initials(tmp_path, capsys):
    from researchclaw.codex.cli import main
    session = prepared(tmp_path)['session']
    submit(tmp_path, session)
    binding = current_corpus(tmp_path)['corpus_binding']
    assert main(['m1', 'corpus', 'decide', str(tmp_path), '--binding', binding, '--decision', 'approve',
                 '--note', 'Synthetic renewed declaration', '--command-id', 'renew', '--json']) == 0
    captured = capsys.readouterr()
    assert 'Independent reasoning' not in captured.out
    assert not captured.err
    json.loads(captured.out)


def test_readonly_packet_rejects_changed_binding_and_resume_explains_wait(tmp_path):
    from researchclaw.core.m1.project import resume_project
    session = prepared(tmp_path)['session']
    checkpoint(tmp_path, files={'knowledge/synthesis.json': b'{}'})
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_council_input_changed'):
        api().read_reviewer_packet(tmp_path, session_id=session['id'], assignment_id='A1')
    assert resume_project(tmp_path)['action'] == 'await_user'
    assert store.read_head(tmp_path)['id'] == before


def test_registered_packet_ignores_mutable_hypothesis_and_evidence_drafts(tmp_path):
    session = prepared(tmp_path)['session']
    head = store.read_head(tmp_path)
    packets = head['state']['packets'].values()
    for packet in packets:
        for output in packet['allowed_outputs']:
            (tmp_path / packet['work_dir'] / output).write_bytes(b'Unregistered mutable draft')
    before = api().reviewer_packet(session, 'A1')
    assert api().read_reviewer_packet(tmp_path, session_id=session['id'], assignment_id='A1') == before
    submit(tmp_path, session)


def test_duplicate_initial_identifier_across_reviewers_is_rejected(tmp_path):
    session = prepared(tmp_path)['session']
    submit(tmp_path, session)
    with pytest.raises(ValueError, match='m1_initial_id_duplicate'):
        submit(tmp_path, session, 'A2', id='I-A1')


def test_replacement_cannot_reuse_host_or_old_assignment_identity(tmp_path):
    session = prepared(tmp_path)['session']
    for replacement in ({'id': 'A4', 'role_id': 'domain', 'host_task_id': 'host-1'},
                        {'id': 'A1', 'role_id': 'domain', 'host_task_id': 'host-4'}):
        with pytest.raises(ValueError, match='m1_assignment_replacement_reused'):
            api().replace_assignment(tmp_path, session_id=session['id'], assignment_id='A1',
                replacement=replacement, reason='Synthetic failure', command_id='replace')
