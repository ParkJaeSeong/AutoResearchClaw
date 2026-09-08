"""Decision gates exercised with synthetic declared-only council submissions."""
from copy import deepcopy
import importlib
import importlib.util
import json

import pytest

from researchclaw.core.m1 import store
from tests.codex_native.m1.test_council import prepared
from tests.codex_native.m1.test_issues import (
    council_api, disclosed, disposition, final_payload, finish_responses,
)


def api():
    name = 'researchclaw.core.m1.decisions'
    assert importlib.util.find_spec(name), 'M1 decision engine is missing'
    return importlib.import_module(name)


def ready_positions():
    return [{'role_id': role, 'recommendation': 'ready'}
            for role in ('domain', 'methodology', 'critical_reproducibility')]


@pytest.mark.parametrize(('positions', 'blockers', 'selected', 'approval', 'codes', 'action'), [
    (ready_positions()[:2], [], ['H1'], True, ['missing_final_role'], 'defer'),
    (ready_positions() + [ready_positions()[0]], [], ['H1'], True, ['duplicate_final_role'], 'defer'),
    (ready_positions(), [], ['H1'], False, ['approval_not_current'], 'defer'),
    (ready_positions(), [], [], True, ['no_selected_hypothesis'], 'stop'),
    (ready_positions(), ['I1'], ['H1'], True, ['open_blockers'], 'return'),
    ([*ready_positions()[:2], {'role_id': 'critical_reproducibility', 'recommendation': 'revise'}],
     [], ['H1'], True, ['opposed_final_role'], 'return'),
    ([*ready_positions()[:2], {'role_id': 'critical_reproducibility', 'recommendation': 'defer'}],
     [], ['H1'], True, ['deferred_final_role'], 'defer'),
    (ready_positions()[:2], ['I1'], [], False,
     ['missing_final_role', 'approval_not_current', 'no_selected_hypothesis', 'open_blockers'], 'defer'),
])
def test_readiness_collects_every_gate_without_majority_override(positions, blockers, selected, approval, codes, action):
    result = api().assess_readiness(positions=positions, open_blockers=blockers,
                                   selected_ids=selected, approval_current=approval)
    assert result['ready'] is False
    assert result['reason_codes'] == codes
    assert result['next_action'] == action


def test_readiness_with_limits_only_allows_design_handoff_and_does_not_mutate():
    positions = ready_positions()
    positions[1]['recommendation'] = 'ready_with_limits'
    original = deepcopy(positions)
    result = api().assess_readiness(positions=positions, open_blockers=[], selected_ids=['H1'], approval_current=True)
    assert result == {'ready': True, 'reason_codes': [], 'next_action': 'handoff', 'message': '설계로 인계 가능'}
    assert positions == original


@pytest.mark.parametrize('positions', [[None], [{'role_id': []}], [
    *ready_positions(), {'role_id': 'author', 'recommendation': 'ready'}]])
def test_malformed_or_unexpected_roles_do_not_crash_or_proceed(positions):
    result = api().assess_readiness(positions=positions, open_blockers=[], selected_ids=['H1'], approval_current=True)
    assert result['ready'] is False
    assert 'invalid_final_role' in result['reason_codes']


def completed(root, *, ready=False):
    session = finish_responses(root, disclosed(root, issue_assignments=() if ready else ('A1',)))
    for assignment_id in ('A1', 'A2', 'A3'):
        council_api().register_final_position(root, session_id=session['id'], assignment_id=assignment_id,
            payload=final_payload(session, assignment_id,
                dispositions=[] if ready else [disposition('issue-A1')],
                recommendation='ready_with_limits' if ready else 'revise'), command_id='final-' + assignment_id)
    return store.read_head(root)['state']['sessions'][session['id']]


def decision_payload(session, *, ready=False):
    finals = deepcopy(session['disclosed_final_positions'])
    issue_ids = [] if ready else ['issue-A1']
    return {'schema_version': 1, 'id': 'decision-one', 'session_id': session['id'],
        'input_binding': session['input_binding'], 'positions': finals,
        'hypothesis_dispositions': [{'hypothesis_ref': ref, 'disposition': 'selected' if ready else 'revise',
            'rationale': 'Synthetic disposition based on all three final positions.',
            'issue_ids': issue_ids, 'final_assignment_ids': ['A1', 'A2', 'A3']} for ref in session['hypothesis_refs']],
        'selected_hypothesis_ids': ['H1'] if ready else [], 'dissent': [] if ready else deepcopy(finals),
        'limitations': ['Synthetic abstract-only evidence.'], 'issue_ids': issue_ids,
        'rationale': 'Synthetic final opinions permit design handoff.' if ready else 'All three roles require revision.',
        'ready': ready, 'reason_codes': [] if ready else ['no_selected_hypothesis', 'open_blockers', 'opposed_final_role'],
        'next_action': 'handoff' if ready else 'return', 'return_target': None if ready else 'hypothesize',
        'proposed_work': [] if ready else ['Revise the causal claim and register supporting evidence.']}


def decide(root, session, payload, command_id='decide'):
    return api().register_decision(root, session_id=session['id'], payload=payload, command_id=command_id)


@pytest.mark.parametrize('ready', [False, True])
def test_register_preserves_exact_finals_candidate_reasons_and_dissent_without_transition(tmp_path, ready):
    session = completed(tmp_path, ready=ready)
    payload = decision_payload(session, ready=ready)
    before = store.read_head(tmp_path)
    result = decide(tmp_path, session, payload)
    head = store.read_head(tmp_path)
    decision = result['decision']
    assert decision['positions'] == session['disclosed_final_positions']
    assert decision['dissent'] == payload['dissent']
    assert decision['hypothesis_dispositions'] == payload['hypothesis_dispositions']
    assert decision['provenance_status'] == 'declared_only'
    assert result['ready'] is ready
    assert result['next_action'] == ('handoff' if ready else 'return')
    assert head['state']['current_node_id'] == 'review'
    assert head['state']['attempts'][-2] == before['state']['attempts'][-2]
    assert head['state']['decisions'] == [decision]
    assert head['state']['sessions'][session['id']]['decision_id'] == decision['id']
    if not ready:
        assert decision['issue_threads'][0]['issue']['id'] == 'issue-A1'
        assert len(decision['issue_threads'][0]['final_dispositions']) == 3


@pytest.mark.parametrize('mutation', ['majority', 'omit_final', 'rewrite_final', 'omit_dissent',
    'omit_candidate', 'duplicate_candidate', 'old_revision', 'unknown_selected', 'omit_issue',
    'omit_candidate_issue', 'omit_candidate_role', 'invent_dissent', 'blank_work', 'wrong_action',
    'wrong_reason', 'malformed_candidate', 'malformed_ids', 'claim_execution', 'wrong_binding'])
def test_decision_rejects_conflicts_without_mutating_head(tmp_path, mutation):
    session = completed(tmp_path)
    value = decision_payload(session)
    if mutation == 'majority': value.update(ready=True, reason_codes=[], next_action='handoff', return_target=None)
    elif mutation == 'omit_final': value['positions'].pop()
    elif mutation == 'rewrite_final': value['positions'][0]['recommendation'] = 'ready'
    elif mutation == 'omit_dissent': value['dissent'].pop()
    elif mutation == 'invent_dissent': value['dissent'][0]['rationale'] = 'Invented'
    elif mutation == 'omit_candidate': value['hypothesis_dispositions'] = []
    elif mutation == 'duplicate_candidate': value['hypothesis_dispositions'] *= 2
    elif mutation == 'old_revision': value['hypothesis_dispositions'][0]['hypothesis_ref']['revision'] = 0
    elif mutation == 'unknown_selected': value['selected_hypothesis_ids'] = ['H9']
    elif mutation == 'omit_issue': value['issue_ids'] = []
    elif mutation == 'omit_candidate_issue': value['hypothesis_dispositions'][0]['issue_ids'] = []
    elif mutation == 'omit_candidate_role': value['hypothesis_dispositions'][0]['final_assignment_ids'].pop()
    elif mutation == 'blank_work': value['proposed_work'] = []
    elif mutation == 'wrong_action': value['next_action'] = 'defer'
    elif mutation == 'wrong_reason': value['reason_codes'] = []
    elif mutation == 'malformed_candidate': value['hypothesis_dispositions'] = [None]
    elif mutation == 'malformed_ids': value['issue_ids'] = [{}]
    elif mutation == 'claim_execution': value['provenance_status'] = 'verified'
    elif mutation == 'wrong_binding': value['input_binding'] = 'changed'
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_decision_(conflict|invalid|binding_invalid)'):
        decide(tmp_path, session, value)
    assert store.read_head(tmp_path)['id'] == before


def test_decision_requires_complete_final_phase(tmp_path):
    session = prepared(tmp_path)['session']
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_council_phase'):
        decide(tmp_path, session, {})
    assert store.read_head(tmp_path)['id'] == before


@pytest.mark.parametrize('change', ['evidence', 'approval'])
def test_decision_rejects_stale_evidence_or_revoked_approval(tmp_path, change):
    from tests.codex_native.m1.helpers import checkpoint
    from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
    session = completed(tmp_path, ready=True)
    if change == 'evidence': checkpoint(tmp_path, files={'knowledge/synthesis.json': b'{}'})
    else:
        record_corpus_approval(tmp_path, corpus_binding=current_corpus(tmp_path)['corpus_binding'],
            decision='reject', note='Synthetic revocation', command_id='revoke')
    before = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='m1_council_input_changed|m1_corpus_approval_required'):
        decide(tmp_path, session, decision_payload(session, ready=True))
    assert store.read_head(tmp_path)['id'] == before


def test_decision_replays_original_receipt_and_rejects_changed_second_decision(tmp_path):
    session = completed(tmp_path)
    value = decision_payload(session)
    first = decide(tmp_path, session, value)
    assert decide(tmp_path, session, value) == first
    alias = decide(tmp_path, session, value, 'alias')
    assert alias['decision'] == first['decision']
    assert len(store.read_head(tmp_path)['state']['decisions']) == 1
    with pytest.raises(ValueError, match='m1_decision_conflict'):
        decide(tmp_path, session, {**value, 'rationale': 'Changed decision'}, 'changed')
    with pytest.raises(ValueError, match='m1_command_conflict'):
        decide(tmp_path, session, {**value, 'rationale': 'Changed request'})


def test_cli_registers_decision_without_assignment_flag(tmp_path, capsys):
    from researchclaw.codex.cli import main
    session = completed(tmp_path)
    path = tmp_path / 'decision.json'
    path.write_text(json.dumps(decision_payload(session)))
    assert main(['m1', 'council', 'decide', str(tmp_path), '--session', session['id'],
        '--submission', str(path), '--command-id', 'cli-decide', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['next_action'] == 'return' and result['ready'] is False


@pytest.mark.parametrize('outcome', ['ready', 'return_hypothesis'])
def test_public_review_fixture_builds_declared_council_and_decision(tmp_path, outcome):
    from tests.codex_native.m1 import helpers
    assert hasattr(helpers, 'build_review_case'), 'Public review fixture is missing'
    result = helpers.build_review_case(tmp_path, outcome=outcome)
    assert set(result) == {'root', 'head_id', 'review_attempt_id', 'decision_id', 'hypothesis_id'}
    head = store.read_head(tmp_path)
    assert result['head_id'] == head['id']
    assert result['hypothesis_id'] == 'H1'
    decision = head['state']['decisions'][0]
    assert decision['id'] == result['decision_id']
    assert decision['ready'] is (outcome == 'ready')
    assert decision['provenance_status'] == 'declared_only'
    assert head['state']['content_origin'] == 'synthetic'
    session = head['state']['sessions'][decision['session_id']]
    assert result['review_attempt_id'] == session['review_attempt_id']
    assert len(session['initials']) == len(session['responses']) == len(session['final_positions']) == 3


def test_public_review_fixture_rejects_unknown_outcome_before_creating_project(tmp_path):
    from tests.codex_native.m1 import helpers
    assert hasattr(helpers, 'build_review_case'), 'Public review fixture is missing'
    with pytest.raises(ValueError, match='outcome'):
        helpers.build_review_case(tmp_path / 'unused', outcome='manufactured_success')
    assert not (tmp_path / 'unused').exists()


def test_every_candidate_gets_independent_selected_deferred_or_rejected_reason(tmp_path):
    from tests.codex_native.m1.test_assignments import assignments
    from tests.codex_native.m1.test_council import initial
    from tests.codex_native.m1.test_hypotheses import prepare_case, register, candidate, envelope
    packet = prepare_case(tmp_path)
    register(tmp_path, packet, envelope(candidate(disposition='rejected'),
        candidate(id='H2', disposition='selected'), candidate(id='H3')))
    session = council_api().prepare_council(tmp_path, attempt_id=packet['attempt_id'],
        assignments=assignments(), command_id='prepare-council')['session']
    for assignment_id in ('A1', 'A2', 'A3'):
        council_api().register_initial(tmp_path, session_id=session['id'], assignment_id=assignment_id,
            payload=initial(session, assignment_id), command_id='initial-' + assignment_id)
    session = finish_responses(tmp_path, session)
    for assignment_id in ('A1', 'A2', 'A3'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id=assignment_id,
            payload=final_payload(session, assignment_id, dispositions=[], recommendation='ready_with_limits'),
            command_id='final-' + assignment_id)
    session = store.read_head(tmp_path)['state']['sessions'][session['id']]
    payload = decision_payload(session, ready=True)
    for record, status, reason in zip(payload['hypothesis_dispositions'],
            ('selected', 'deferred', 'rejected'),
            ('Prioritize the direct observation.', 'Await comparable data.', 'Existing evidence favors an alternative.')):
        record.update(disposition=status, rationale=reason)
    before = store.read_head(tmp_path)['state']['artifacts']
    value = decide(tmp_path, session, payload)['decision']
    assert value['selected_hypothesis_ids'] == ['H1']
    assert [(d['hypothesis_ref']['id'], d['disposition'], d['rationale'])
            for d in value['hypothesis_dispositions']] == [
        ('H1', 'selected', 'Prioritize the direct observation.'),
        ('H2', 'deferred', 'Await comparable data.'),
        ('H3', 'rejected', 'Existing evidence favors an alternative.')]
    assert store.read_head(tmp_path)['state']['artifacts'] == before


def test_open_minor_dissent_is_preserved_even_with_ready_recommendations(tmp_path):
    from tests.codex_native.m1.test_council import initial
    from tests.codex_native.m1.test_issues import open_issue
    session = prepared(tmp_path)['session']
    for assignment_id in ('A1', 'A2', 'A3'):
        payload = initial(session, assignment_id)
        if assignment_id == 'A1':
            payload['open_issues'] = [open_issue(session, severity='minor')]
        council_api().register_initial(tmp_path, session_id=session['id'], assignment_id=assignment_id,
            payload=payload, command_id='initial-' + assignment_id)
    session = finish_responses(tmp_path, session)
    for assignment_id in ('A1', 'A2', 'A3'):
        council_api().register_final_position(tmp_path, session_id=session['id'], assignment_id=assignment_id,
            payload=final_payload(session, assignment_id, dispositions=[disposition('issue-A1')],
                                  recommendation='ready_with_limits'), command_id='final-' + assignment_id)
    session = store.read_head(tmp_path)['state']['sessions'][session['id']]
    payload = decision_payload(session, ready=True)
    payload.update(issue_ids=['issue-A1'], dissent=deepcopy(session['disclosed_final_positions']))
    payload['hypothesis_dispositions'][0]['issue_ids'] = ['issue-A1']
    value = decide(tmp_path, session, payload)['decision']
    assert value['ready'] is True
    assert len(value['dissent']) == 3
    assert value['issue_threads'][0]['status'] == 'open'
    assert value['open_blockers'] == []
