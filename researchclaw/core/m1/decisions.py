"""Conservative design-handoff readiness from frozen council finals.

No scores, votes, host execution attestation or graph transition is produced.
Candidate dispositions are coordinator declarations linked to preserved finals.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import store
from .council import _current, _public_result, _record_map, _session
from .issues import build_issue_threads
from .packets import _commit, _current_attempt, _mutation, _replay, _request

REQUIRED_ROLES = {'domain', 'methodology', 'critical_reproducibility'}
PROCEED_RECOMMENDATIONS = {'ready', 'ready_with_limits'}
_FIELDS = {'schema_version', 'id', 'session_id', 'input_binding', 'positions',
           'hypothesis_dispositions', 'selected_hypothesis_ids', 'dissent', 'limitations',
           'issue_ids', 'rationale', 'ready', 'reason_codes', 'next_action', 'return_target', 'proposed_work'}
_CANDIDATE_FIELDS = {'hypothesis_ref', 'disposition', 'rationale', 'issue_ids', 'final_assignment_ids'}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return (type(value) is list and all(_text(v) for v in value)
            and len(set(value)) == len(value))


def assess_readiness(*, positions: list[dict], open_blockers: list[str],
                     selected_ids: list[str], approval_current: bool) -> dict:
    """Collect every failed gate before selecting the conservative next action."""
    reasons = []
    values = positions if type(positions) is list else []
    valid = [p for p in values if type(p) is dict and _text(p.get('role_id'))]
    roles = [p['role_id'] for p in valid]
    if (type(positions) is not list or len(valid) != len(values)
            or set(roles) - REQUIRED_ROLES):
        reasons.append('invalid_final_role')
    if len(set(roles)) != len(roles):
        reasons.append('duplicate_final_role')
    if REQUIRED_ROLES - set(roles):
        reasons.append('missing_final_role')
    if approval_current is not True:
        reasons.append('approval_not_current')
    if not _strings(selected_ids):
        reasons.append('invalid_selected_hypotheses')
    if not selected_ids:
        reasons.append('no_selected_hypothesis')
    if not _strings(open_blockers):
        reasons.append('invalid_open_blockers')
    elif open_blockers:
        reasons.append('open_blockers')
    recommendations = [p.get('recommendation') for p in valid]
    if any(not _text(r) or r not in PROCEED_RECOMMENDATIONS | {'revise', 'defer'} for r in recommendations):
        reasons.append('invalid_final_recommendation')
    if 'revise' in recommendations:
        reasons.append('opposed_final_role')
    if 'defer' in recommendations:
        reasons.append('deferred_final_role')
    wait_codes = {'invalid_final_role', 'duplicate_final_role', 'missing_final_role',
                  'approval_not_current', 'invalid_selected_hypotheses', 'invalid_open_blockers',
                  'invalid_final_recommendation', 'deferred_final_role'}
    if not reasons:
        action = 'handoff'
    elif wait_codes.intersection(reasons):
        action = 'defer'
    elif {'open_blockers', 'opposed_final_role'}.intersection(reasons):
        action = 'return'
    else:
        action = 'stop'
    return {'ready': not reasons, 'reason_codes': reasons, 'next_action': action,
            'message': '설계로 인계 가능' if not reasons else '설계 인계 보류'}


def _same(left, right):
    """JSON equality must not let Python's True == 1 rewrite a frozen record."""
    return store._canonical(left) == store._canonical(right)


def _validate(payload, session):
    if (type(payload) is not dict or set(payload) != _FIELDS
            or type(payload.get('schema_version')) is not int or payload['schema_version'] != 1
            or not _text(payload.get('id')) or not _text(payload.get('rationale'))
            or type(payload.get('ready')) is not bool
            or any(not _strings(payload.get(key)) for key in
                   ('selected_hypothesis_ids', 'limitations', 'issue_ids', 'reason_codes', 'proposed_work'))
            or type(payload.get('hypothesis_dispositions')) is not list
            or payload.get('next_action') not in ('handoff', 'return', 'defer', 'stop')):
        raise ValueError('m1_decision_invalid')
    if payload['session_id'] != session['id'] or payload['input_binding'] != session['input_binding']:
        raise ValueError('m1_decision_binding_invalid')
    if ((payload['next_action'] == 'return' and not _text(payload['return_target']))
            or (payload['next_action'] != 'return' and payload['return_target'] is not None)
            or (payload['next_action'] != 'handoff' and not payload['proposed_work'])):
        raise ValueError('m1_decision_invalid')
    finals = session['disclosed_final_positions']
    final_map = _record_map(session['final_positions'])
    assignments = {a['id'] for a in session['assignments']}
    if (set(final_map) != assignments
            or not _same(finals, [final_map[key] for key in sorted(assignments)])
            or not _same(payload['positions'], finals)):
        raise ValueError('m1_decision_conflict')
    dissent = [p for p in finals if p['recommendation'] not in PROCEED_RECOMMENDATIONS
               or any(d['status'] == 'open' for d in p['issue_dispositions'])]
    if not _same(payload['dissent'], dissent):
        raise ValueError('m1_decision_conflict')
    # Use frozen disclosure snapshots, never caller-supplied issue summaries.
    threads = list(build_issue_threads({**session, 'initials': {},
        'responses': session['disclosed_responses'], 'final_positions': finals}))
    if set(payload['issue_ids']) != {t['issue']['id'] for t in threads}:
        raise ValueError('m1_decision_conflict')
    seen = []
    selected = []
    for value in payload['hypothesis_dispositions']:
        if (type(value) is not dict or set(value) != _CANDIDATE_FIELDS
                or type(value.get('hypothesis_ref')) is not dict
                or set(value['hypothesis_ref']) != {'id', 'revision'}
                or not _text(value['hypothesis_ref'].get('id'))
                or type(value['hypothesis_ref'].get('revision')) is not int
                or value.get('disposition') not in ('selected', 'deferred', 'rejected', 'revise')
                or not _text(value.get('rationale')) or not _strings(value.get('issue_ids'))
                or not _strings(value.get('final_assignment_ids'))):
            raise ValueError('m1_decision_invalid')
        ref = value['hypothesis_ref']
        if ref not in session['hypothesis_refs'] or ref in seen:
            raise ValueError('m1_decision_conflict')
        seen.append(ref)
        targeted = {t['issue']['id'] for t in threads if ref in t['issue']['target_refs']}
        if set(value['issue_ids']) != targeted or set(value['final_assignment_ids']) != assignments:
            raise ValueError('m1_decision_conflict')
        if value['disposition'] == 'selected':
            selected.append(ref['id'])
    if len(seen) != len(session['hypothesis_refs']) or set(selected) != set(payload['selected_hypothesis_ids']):
        raise ValueError('m1_decision_conflict')
    blockers = sorted(t['issue']['id'] for t in threads
                      if t['issue']['severity'] == 'blocking' and t['status'] == 'open')
    # _current already requires the session's exact current approved corpus.
    policy = assess_readiness(positions=finals, open_blockers=blockers,
                              selected_ids=selected, approval_current=True)
    if any(payload[key] != policy[key] for key in ('ready', 'reason_codes', 'next_action')):
        raise ValueError('m1_decision_conflict')
    return {**deepcopy(payload), **store._VERSION, 'issue_threads': threads,
            'open_blockers': blockers, 'message': policy['message'],
            'review_attempt_id': session['review_attempt_id'], 'source_attempt_id': session['source_attempt_id'],
            'approval_id': session['approval_id'], 'provenance_status': 'declared_only',
            'content_origin': session['content_origin']}


def register_decision(root: Path, *, session_id: str, payload: dict, command_id: str) -> dict:
    """Record one coordinator decision without advancing or editing research."""
    request = _request(command_id, {'operation': 'register_decision', 'session_id': session_id, 'payload': payload})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        state = head['state']
        session = _session(state, session_id)
        _current(root, head, session)
        prior = next((d for d in state.get('decisions', []) if d['session_id'] == session_id), None)
        digest = store._hash(store._canonical(request['payload']))
        if prior is not None:
            if prior['submission_sha256'] != digest:
                raise ValueError('m1_decision_conflict')
            value, objects, event_type = prior, {}, 'council_decision_replayed'
        else:
            if session['status'] != 'final_positions_complete':
                raise ValueError('m1_council_phase')
            value = _validate(request['payload'], session)
            if any(d['id'] == value['id'] for d in state.get('decisions', [])):
                raise ValueError('m1_decision_conflict')
            value['submission_sha256'] = digest
            state.setdefault('decisions', []).append(value)
            state['selected_hypothesis_ids'] = deepcopy(value['selected_hypothesis_ids'])
            state['open_blockers'] = deepcopy(value['open_blockers'])
            session['decision_id'] = value['id']
            session['status'] = 'decided'
            _current_attempt(state)['status'] = 'decided'
            _current_attempt(state)['decision_id'] = value['id']
            objects = {f"councils/{session_id}/decisions/{digest}.json": store._canonical(value)}
            event_type = 'council_decision_registered'
        result = {'session_id': session_id, 'decision_id': value['id'], 'decision': deepcopy(value),
                  **{key: value[key] for key in ('ready', 'reason_codes', 'next_action', 'message')}}
        return _public_result(_commit(root, head, command_id, request, result,
                                     event_type=event_type, objects=objects))
