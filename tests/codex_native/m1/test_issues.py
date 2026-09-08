"""Synthetic council records; these tests do not claim actual role execution."""
from copy import deepcopy
import importlib
import json

import pytest

from researchclaw.core.m1 import store
from tests.codex_native.m1.test_council import initial, prepared


def issues_api():
    return importlib.import_module('researchclaw.core.m1.issues')


def council_api():
    return importlib.import_module('researchclaw.core.m1.council')


def open_issue(session, assignment_id='A1', issue_id='issue-A1', *, severity='blocking', **updates):
    value = {'id': issue_id, 'raised_by': assignment_id,
             'target_refs': [{'id': 'H1', 'revision': 1}], 'evidence_refs': [],
             'question': 'What evidence closes ' + issue_id + '?',
             'impact': 'The unresolved claim changes the review outcome.',
             'severity': severity, 'resolution_condition': 'Register direct supporting evidence.'}
    value.update(updates)
    return value


def response_payload(session, assignment_id='A1', *, responses=None, new_issues=None, **updates):
    assignment = next(a for a in session['assignments'] if a['id'] == assignment_id)
    value = {'schema_version': 1, 'id': 'response-' + assignment_id,
             'session_id': session['id'], 'assignment_id': assignment_id,
             'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id'],
             'input_binding': session['input_binding'],
             'rationale': 'I considered the disclosed positions and recorded every response I have.',
             'responses': responses or [], 'new_issues': new_issues or []}
    value.update(updates)
    return value


def response_record(own_assignment_id, issue_id='issue-A1', *, response_id=None, **updates):
    value = {'id': response_id or 'reply-' + own_assignment_id, 'issue_id': issue_id,
             'assignment_id': own_assignment_id, 'stance': 'challenge',
             'rationale': 'The disclosed evidence does not establish the claim.', 'evidence_refs': []}
    value.update(updates)
    return value


def final_payload(session, assignment_id='A1', *, dispositions, **updates):
    assignment = next(a for a in session['assignments'] if a['id'] == assignment_id)
    value = {'schema_version': 1, 'session_id': session['id'], 'assignment_id': assignment_id,
             'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id'],
             'input_binding': session['input_binding'], 'recommendation': 'revise',
             'change_rationale': 'The response round clarified which objections remain open.',
             'issue_dispositions': dispositions, 'rationale': 'Revision is required before selection.',
             'evidence_refs': []}
    value.update(updates)
    return value


def disposition(issue_id, *, status='open', response_ids=None, evidence_refs=None):
    return {'issue_id': issue_id, 'status': status,
            'rationale': 'The stated resolution condition has not yet been met.',
            'response_ids': response_ids or [], 'evidence_refs': evidence_refs or []}


def disclosed(root, *, issue_assignments=('A1',)):
    session = prepared(root)['session']
    for assignment_id in ('A1', 'A2', 'A3'):
        payload = initial(session, assignment_id)
        if assignment_id in issue_assignments:
            payload['open_issues'] = [open_issue(session, assignment_id, 'issue-' + assignment_id)]
        council_api().register_initial(root, session_id=session['id'], assignment_id=assignment_id,
                                       payload=payload, command_id='initial-' + assignment_id)
    return store.read_head(root)['state']['sessions'][session['id']]


def register_response(root, session, assignment_id, *, payload=None, command_id=None):
    return council_api().register_response(root, session_id=session['id'], assignment_id=assignment_id,
        payload=payload or response_payload(session, assignment_id),
        command_id=command_id or 'response-' + assignment_id)


def finish_responses(root, session, payloads=None):
    for assignment_id in ('A1', 'A2', 'A3'):
        register_response(root, session, assignment_id,
                          payload=(payloads or {}).get(assignment_id))
    return store.read_head(root)['state']['sessions'][session['id']]


def test_response_to_unknown_issue_is_rejected():
    response = {'id': 'R1', 'issue_id': 'I2', 'assignment_id': 'A1',
                'stance': 'challenge', 'rationale': 'scope differs', 'evidence_refs': ['C1']}
    problems = issues_api().validate_response(response, issue_ids={'I1'}, assignment_ids={'A1'})
    assert any(x['code'] == 'm1_unknown_issue' for x in problems)


@pytest.mark.parametrize(('updates', 'code'), [
    ({'stance': 'agree'}, 'm1_response_invalid'),
    ({'assignment_id': 'A9'}, 'm1_unknown_assignment'),
    ({'rationale': ' '}, 'm1_response_invalid'),
    ({'evidence_refs': 'artifact'}, 'm1_response_invalid'),
    ({'extra': True}, 'm1_response_invalid'),
])
def test_response_record_contract_reports_specific_problems(updates, code):
    value = response_record('A1', issue_id='I1', **updates)
    assert code in {p['code'] for p in issues_api().validate_response(
        value, issue_ids={'I1'}, assignment_ids={'A1'})}


def test_packet_declares_exact_response_then_final_contract_without_mutating_assignment(tmp_path):
    session = disclosed(tmp_path)
    packet = council_api().reviewer_packet(session, 'A1')
    assert packet['phase'] == 'response'
    assert packet['own_assignment']['allowed_outputs'] == ['initial']
    assert packet['phase_allowed_outputs'] == ['response']
    assert packet['output_contract']['operation'] == 'register_response'
    assert packet['output_contract']['required_fields'] == sorted({
        'schema_version', 'id', 'session_id', 'assignment_id', 'role_id', 'host_task_id',
        'input_binding', 'rationale', 'responses', 'new_issues'})
    assert packet['output_contract']['responses']['stance'] == [
        'accept', 'partly_accept', 'challenge', 'insufficient_evidence']
    finish_responses(tmp_path, session)
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    packet = council_api().reviewer_packet(current, 'A1')
    assert packet['phase'] == 'final'
    assert packet['phase_allowed_outputs'] == ['final_position']
    assert packet['output_contract']['operation'] == 'register_final_position'
    assert packet['output_contract']['recommendation'] == ['ready', 'ready_with_limits', 'revise', 'defer']


def test_each_role_registers_one_real_response_bundle_and_empty_bundle_needs_reason(tmp_path):
    session = disclosed(tmp_path)
    bad = response_payload(session, rationale=' ')
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_response_bundle_invalid'):
        register_response(tmp_path, session, 'A1', payload=bad)
    assert store.read_head(tmp_path)['id'] == before
    first = register_response(tmp_path, session, 'A1',
                              payload=response_payload(session, rationale='No issue-specific response to add.'))
    assert first['submitted_assignment_ids'] == ['A1']
    with pytest.raises(ValueError, match='m1_response_conflict'):
        register_response(tmp_path, session, 'A1',
                          payload=response_payload(session, rationale='Changed second round.'), command_id='changed')
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    assert list(current['responses']) == ['A1']


def test_response_validation_binds_issue_identity_evidence_and_new_issue_links(tmp_path):
    session = disclosed(tmp_path)
    allowed = session['input_refs'][0]['id']
    reply = response_record('A2', evidence_refs=[allowed])
    linked = open_issue(session, 'A2', 'issue-new', severity='major', related_issue_ids=['issue-A1'])
    payload = response_payload(session, 'A2', responses=[reply], new_issues=[linked])
    register_response(tmp_path, session, 'A2', payload=payload)
    stored = store.read_head(tmp_path)['state']['sessions'][session['id']]['responses']['A2']
    assert stored['responses'] == [reply]
    assert stored['new_issues'][0]['related_issue_ids'] == ['issue-A1']
    assert stored['new_issues'][0]['raised_by'] == 'A2'
    assert stored['new_issues'][0]['session_id'] == session['id']

    for suffix, mutation, error in (
        ('unknown', {'responses': [response_record('A3', 'missing')]}, 'm1_unknown_issue'),
        ('other', {'responses': [response_record('A2', assignment_id='A1')]}, 'm1_response_binding_invalid'),
        ('evidence', {'responses': [response_record('A3', evidence_refs=['missing'])]}, 'm1_response_evidence_invalid'),
        ('relation', {'new_issues': [open_issue(session, 'A3', 'issue-bad', related_issue_ids=['future'])]},
         'm1_response_issue_invalid'),
    ):
        bad = response_payload(session, 'A3', **mutation)
        before = store.read_head(tmp_path)['id']
        with pytest.raises(ValueError, match=error):
            register_response(tmp_path, session, 'A3', payload=bad, command_id='bad-' + suffix)
        assert store.read_head(tmp_path)['id'] == before


def test_final_is_blocked_until_every_role_responds_and_must_disposition_every_issue(tmp_path):
    session = disclosed(tmp_path)
    register_response(tmp_path, session, 'A1')
    with pytest.raises(ValueError, match='m1_council_phase'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=final_payload(session, dispositions=[disposition('issue-A1')]), command_id='early-final')
    session = finish_responses(tmp_path, session, payloads={})
    with pytest.raises(ValueError, match='m1_final_issue_dispositions_invalid'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=final_payload(session, dispositions=[]), command_id='missing-issue')
    with pytest.raises(ValueError, match='m1_final_response_ref_invalid'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=final_payload(session, dispositions=[disposition('issue-A1', response_ids=['missing'])]),
            command_id='missing-response')


def test_malformed_final_issue_identifier_is_a_validation_error(tmp_path):
    session = finish_responses(tmp_path, disclosed(tmp_path))
    malformed = disposition('issue-A1')
    malformed['issue_id'] = {'not': 'an ID'}
    with pytest.raises(ValueError, match='m1_final_issue_dispositions_invalid'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=final_payload(session, dispositions=[malformed]), command_id='malformed-issue-id')


def test_final_response_references_must_be_unique(tmp_path):
    session = disclosed(tmp_path)
    session = finish_responses(tmp_path, session, payloads={
        'A2': response_payload(session, 'A2', responses=[response_record('A2', response_id='reply-A2')])})
    duplicate = disposition('issue-A1', response_ids=['reply-A2', 'reply-A2'])
    with pytest.raises(ValueError, match='m1_final_issue_dispositions_invalid'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload=final_payload(session, dispositions=[duplicate]), command_id='duplicate-response-ref')


def test_issue_threads_preserve_sources_responses_and_raiser_confirmed_resolution(tmp_path):
    session = disclosed(tmp_path)
    reply = response_record('A2', response_id='reply-A2')
    new_issue = open_issue(session, 'A2', 'issue-response-A2', severity='major',
                           related_issue_ids=['issue-A1'])
    response_a2 = response_payload(session, 'A2', responses=[reply], new_issues=[new_issue])
    session = finish_responses(tmp_path, session, payloads={'A2': response_a2})
    finals = {
        'A1': [disposition('issue-A1', status='resolved', response_ids=['reply-A2']),
               disposition('issue-response-A2', status='open')],
        'A2': [disposition('issue-A1', status='open', response_ids=['reply-A2']),
               disposition('issue-response-A2', status='resolved')],
        'A3': [disposition('issue-A1', status='resolved', response_ids=['reply-A2']),
               disposition('issue-response-A2', status='open')],
    }
    for assignment_id in ('A1', 'A2', 'A3'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id=assignment_id,
            payload=final_payload(session, assignment_id, dispositions=finals[assignment_id]),
            command_id='final-' + assignment_id)
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    assert current['status'] == 'final_positions_complete'
    threads = {t['issue']['id']: t for t in issues_api().build_issue_threads(current)}
    assert threads['issue-A1']['issue']['question'].startswith('What evidence')
    assert [r['id'] for r in threads['issue-A1']['responses']] == ['reply-A2']
    assert threads['issue-A1']['status'] == 'resolved'
    assert threads['issue-A1']['resolution_confirmed_by'] == ['A1', 'A3']
    assert threads['issue-response-A2']['status'] == 'open'
    assert threads['issue-response-A2']['resolution_confirmed_by'] == ['A2']
    assert threads['issue-response-A2']['requires_other_role_confirmation'] is True
    assert len(threads['issue-A1']['final_dispositions']) == 3


def test_final_binding_evidence_replay_and_read_only_complete_packet(tmp_path):
    session = finish_responses(tmp_path, disclosed(tmp_path))
    evidence = session['input_refs'][0]['id']
    payload = final_payload(session, dispositions=[disposition('issue-A1', evidence_refs=[evidence])],
                            recommendation='ready_with_limits', evidence_refs=[evidence])
    first = council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
                                                  payload=payload, command_id='final-A1')
    assert council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
                                                 payload=payload, command_id='final-A1') == first
    duplicate = council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
                                                      payload=payload, command_id='final-A1-alias')
    assert duplicate['assignment_id'] == 'A1'
    with pytest.raises(ValueError, match='m1_final_conflict'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
            payload={**payload, 'recommendation': 'ready'}, command_id='changed-final')
    current = store.read_head(tmp_path)['state']['sessions'][session['id']]
    packet = council_api().reviewer_packet(current, 'A1')
    assert packet['phase'] == 'complete'
    assert packet['phase_allowed_outputs'] == []
    assert packet['output_contract']['operation'] == 'final_position_already_registered'


@pytest.mark.parametrize(('updates', 'error'), [
    ({'assignment_id': 'A2'}, 'm1_final_binding_invalid'),
    ({'role_id': 'methodology'}, 'm1_final_binding_invalid'),
    ({'host_task_id': 'host-2'}, 'm1_final_binding_invalid'),
    ({'input_binding': '0' * 64}, 'm1_final_binding_invalid'),
    ({'recommendation': 'approve'}, 'm1_final_position_invalid'),
    ({'change_rationale': ' '}, 'm1_final_position_invalid'),
    ({'evidence_refs': ['not-bound']}, 'm1_final_position_invalid'),
])
def test_final_rejects_other_identity_changed_binding_and_unregistered_evidence(tmp_path, updates, error):
    session = finish_responses(tmp_path, disclosed(tmp_path))
    payload = final_payload(session, dispositions=[disposition('issue-A1')], **updates)
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match=error):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id='A1',
                                              payload=payload, command_id='invalid-final')
    assert store.read_head(tmp_path)['id'] == before


def test_response_and_final_cli_use_submission_contract(tmp_path, capsys):
    from researchclaw.codex.cli import main
    session = disclosed(tmp_path)
    response_file = tmp_path / 'response.json'
    response_file.write_text(json.dumps(response_payload(session)))
    assert main(['m1', 'council', 'response', str(tmp_path), '--session', session['id'],
                 '--assignment', 'A1', '--submission', str(response_file),
                 '--command-id', 'cli-response', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['assignment_id'] == 'A1'
    register_response(tmp_path, session, 'A2')
    register_response(tmp_path, session, 'A3')
    session = store.read_head(tmp_path)['state']['sessions'][session['id']]
    final_file = tmp_path / 'final.json'
    final_file.write_text(json.dumps(final_payload(
        session, dispositions=[disposition('issue-A1')])))
    assert main(['m1', 'council', 'final', str(tmp_path), '--session', session['id'],
                 '--assignment', 'A1', '--submission', str(final_file),
                 '--command-id', 'cli-final', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['assignment_id'] == 'A1'


def test_response_and_final_reject_changed_current_inputs_without_writes(tmp_path):
    from tests.codex_native.m1.helpers import checkpoint
    session = disclosed(tmp_path)
    checkpoint(tmp_path, files={'knowledge/synthesis.json': b'{}'})
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_council_input_changed'):
        register_response(tmp_path, session, 'A1')
    assert store.read_head(tmp_path)['id'] == before

    stable = disclosed(tmp_path / 'second')
    stable = finish_responses(tmp_path / 'second', stable)
    checkpoint(tmp_path / 'second', files={'knowledge/synthesis.json': b'{}'})
    before = store.read_head(tmp_path / 'second')['id']
    with pytest.raises(ValueError, match='m1_council_input_changed'):
        council_api().register_final_position(tmp_path / 'second', session_id=stable['id'], assignment_id='A1',
            payload=final_payload(stable, dispositions=[disposition('issue-A1')]), command_id='stale-final')
    assert store.read_head(tmp_path / 'second')['id'] == before
