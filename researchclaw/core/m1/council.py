"""Independent initial, response and final-position council records.

This is packet isolation, not a sandbox against a host reading the store. The
engine records caller declarations only; native execution observations belong in
separate host evidence. This module records deliberation but makes no decision.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from . import store
from .approvals import CORPUS_PATHS, require_corpus_approval
from .artifacts import read_registered_inputs
from .assignments import ASSIGNMENT_INPUT_FIELDS, JUDGING_ROLES, bind_assignments
from .issues import RESPONSE_FIELDS, RESPONSE_STANCES, build_issue_threads, collect_issues, validate_response
from .packets import _commit, _current_attempt, _mutation, _replay, _request
from .roles import describe_roles

_HYPOTHESIS = 'hypotheses/hypotheses.json'
_INPUT_PATHS = (*CORPUS_PATHS, 'knowledge/extractions.jsonl', 'knowledge/extraction_manifest.json',
                'knowledge/synthesis.json', 'knowledge/synthesis.md', _HYPOTHESIS, 'hypotheses/hypotheses.md')
_INITIAL_FIELDS = {'schema_version', 'id', 'session_id', 'assignment_id', 'role_id', 'host_task_id',
                   'input_binding', 'rationale', 'evidence_refs', 'open_issues'}
_ISSUE_FIELDS = {'id', 'raised_by', 'target_refs', 'evidence_refs', 'question', 'impact',
                 'severity', 'resolution_condition'}
_RESPONSE_BUNDLE_FIELDS = {'schema_version', 'id', 'session_id', 'assignment_id', 'role_id',
                           'host_task_id', 'input_binding', 'rationale', 'responses', 'new_issues'}
_FINAL_FIELDS = {'schema_version', 'session_id', 'assignment_id', 'role_id', 'host_task_id',
                 'input_binding', 'recommendation', 'change_rationale', 'issue_dispositions',
                 'rationale', 'evidence_refs'}
_DISPOSITION_FIELDS = {'issue_id', 'status', 'rationale', 'response_ids', 'evidence_refs'}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value, *, nonempty=False):
    return type(value) is list and (bool(value) or not nonempty) and all(_text(v) for v in value)


def _inputs(root: Path, head: dict, source_id: str) -> dict:
    """Require current registered hypothesis -> synthesis -> extraction -> corpus."""
    state = head['state']
    latest = {ref['logical_path']: ref for ref in state.get('artifacts', [])}
    if any(path not in latest for path in _INPUT_PATHS):
        raise ValueError('m1_council_inputs_missing')
    corpus = require_corpus_approval(root, head)
    producers = {}
    for path, node in ((_HYPOTHESIS, 'hypothesize'), ('knowledge/synthesis.json', 'synthesize'),
                       ('knowledge/extractions.jsonl', 'extract')):
        ref = latest[path]
        matches = [a for a in state['attempts'] if a['id'] == ref['producer_attempt_id']
                   and a['node_id'] == node and ref in a.get('output_refs', [])]
        if len(matches) != 1:
            raise ValueError('m1_council_input_changed')
        producers[node] = matches[0]
    source = producers['hypothesize']
    latest_source = [a for a in state['attempts'] if a['node_id'] == 'hypothesize'][-1]
    if source['id'] != source_id or latest_source['id'] != source_id or source['status'] != 'review_pending':
        raise ValueError('m1_council_input_changed')
    required = {'hypothesize': ('scope/goal.md', 'scope/constraints.json', 'knowledge/synthesis.json',
                                'knowledge/extractions.jsonl'),
                'synthesize': ('scope/goal.md', 'scope/constraints.json', 'knowledge/extractions.jsonl',
                               'knowledge/extraction_manifest.json'), 'extract': CORPUS_PATHS}
    outputs = {'hypothesize': (_HYPOTHESIS, 'hypotheses/hypotheses.md'),
               'synthesize': ('knowledge/synthesis.json', 'knowledge/synthesis.md'),
               'extract': ('knowledge/extractions.jsonl', 'knowledge/extraction_manifest.json')}
    for node, producer in producers.items():
        if any(latest[p] not in producer.get('input_refs', []) for p in required[node]):
            raise ValueError('m1_council_input_changed')
        if any(latest[p] not in producer.get('output_refs', []) for p in outputs[node]):
            raise ValueError('m1_council_input_changed')
    refs = sorted((deepcopy(latest[p]) for p in _INPUT_PATHS), key=lambda r: r['id'])
    if len({r['id'] for r in refs}) != len(refs):
        raise ValueError('m1_input_ref_invalid')
    for ref in refs:
        if head['objects'].get(ref['sha256']) != {'sha256': ref['sha256'], 'size': ref['size']}:
            raise ValueError('m1_input_ref_invalid')
    files = read_registered_inputs(root, refs)
    hypotheses = json.loads(files[_HYPOTHESIS], object_pairs_hook=store._unique_pairs)['hypotheses']
    current = {}
    for h in hypotheses:
        if h['id'] not in current or h['revision'] > current[h['id']]['revision']:
            current[h['id']] = h
    authors = sorted({h['author_assignment_id'] for h in hypotheses})
    # Author host metadata is optional, and is itself only a declaration.
    author_hosts = sorted({h['author_host_task_id'] for h in hypotheses if _text(h.get('author_host_task_id'))})
    for assignment in state.get('assignments', []):
        if assignment.get('id') in authors and _text(assignment.get('host_task_id')):
            author_hosts.append(assignment['host_task_id'])
    binding = store._hash(store._canonical({'packet_version': 1, 'project_id': state['project_id'],
        'source_attempt_id': source_id, 'approval_id': corpus['approval']['id'],
        'objects': [{'id': ref['id'], 'sha256': ref['sha256']} for ref in refs],
        'configuration': {k: state[k] for k in ('topic', 'profile', 'content_origin')}}))
    return {'input_binding': binding, 'input_refs': refs, 'approval_id': corpus['approval']['id'],
            'hypothesis_refs': [{'id': h['id'], 'revision': h['revision']} for _, h in sorted(current.items())],
            'author_assignment_ids': authors, 'author_host_task_ids': sorted(set(author_hosts)),
            'allowed_evidence': [{'ref': ref, 'content': files[ref['logical_path']].decode('utf-8')} for ref in refs]}


def _session(state: dict, session_id: str) -> dict:
    session = state.get('sessions', {}).get(session_id)
    if session is None:
        raise ValueError('m1_council_unknown')
    return session


def _active(session: dict, assignment_id: str) -> dict:
    matches = [a for a in session['assignments'] if a['id'] == assignment_id]
    if len(matches) != 1:
        raise ValueError('m1_assignment_inactive')
    return matches[0]


def _current(root: Path, head: dict, session: dict) -> None:
    attempt = _current_attempt(head['state'])
    if (head['state']['current_node_id'] != 'review' or attempt is None
            or attempt['id'] != session['review_attempt_id'] or attempt['session_id'] != session['id']):
        raise ValueError('m1_council_stale')
    if _inputs(root, head, session['source_attempt_id'])['input_binding'] != session['input_binding']:
        raise ValueError('m1_council_input_changed')


def _public_result(result: dict) -> dict:
    """Mutation receipts never return a raw state/event containing other initials."""
    result = deepcopy(result)
    receipt = result['receipt']
    result['receipt'] = {k: receipt[k] for k in ('schema_version', 'workflow_version', 'id')}
    return result


def _record_map(values) -> dict[str, dict]:
    """Read Task 10's empty-list placeholders and Task 11's keyed records."""
    if type(values) is dict:
        return values
    if type(values) is list:
        if not values:
            return {}
        if all(type(value) is dict and _text(value.get('assignment_id')) for value in values):
            return {value['assignment_id']: value for value in values}
    raise ValueError('m1_council_record_invalid')


def prepare_council(root: Path, *, attempt_id: str, assignments: list[dict], command_id: str) -> dict:
    request = _request(command_id, {'operation': 'prepare_council', 'attempt_id': attempt_id,
                                    'assignments': assignments})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        state = head['state']
        if any(s['source_attempt_id'] == attempt_id for s in state.get('sessions', {}).values()):
            raise ValueError('m1_council_exists')
        attempt = _current_attempt(state)
        if (state['current_node_id'] != 'hypothesize' or attempt is None or attempt['id'] != attempt_id
                or attempt['status'] != 'review_pending'):
            raise ValueError('m1_council_source_not_eligible')
        inputs = _inputs(root, head, attempt_id)
        session_id = 'session-' + uuid4().hex
        review_id = 'attempt-' + uuid4().hex
        bound = bind_assignments(request['assignments'], session_id=session_id,
            input_binding=inputs['input_binding'], author_assignment_ids=set(inputs['author_assignment_ids']),
            author_host_task_ids=set(inputs['author_host_task_ids']))
        session = {**store._VERSION, 'id': session_id, 'source_attempt_id': attempt_id,
            'review_attempt_id': review_id, **inputs, 'assignments': bound, 'assignment_history': [],
            'initials': {}, 'responses': {}, 'final_positions': [], 'disclosed_initials': [],
            'disclosed_responses': [], 'disclosed_final_positions': [],
            'status': 'collecting_initials', 'content_origin': state['content_origin']}
        prior = [a for a in state['attempts'] if a['node_id'] == 'review']
        review = {**store._VERSION, 'id': review_id, 'node_id': 'review',
            'revision': prior[-1]['revision'] + 1 if prior else 1,
            'parent_attempt_id': prior[-1]['id'] if prior else None,
            'source_attempt_id': attempt_id, 'session_id': session_id,
            'input_refs': deepcopy(inputs['input_refs']), 'input_binding': inputs['input_binding'],
            'status': 'collecting_initials', 'output_refs': [],
            'structural_validation': 'not_performed', 'scientific_validation': 'not_performed'}
        state['attempts'].append(review)
        state['current_node_id'] = 'review'
        state.setdefault('sessions', {})[session_id] = session
        return _public_result(_commit(root, head, command_id, request, {'session': deepcopy(session)},
            event_type='council_prepared', objects={f'councils/{session_id}/prepared.json': store._canonical(session)}))


def reviewer_packet(session: dict, assignment_id: str) -> dict:
    """Return only the selected assignment, shared inputs and permitted disclosure."""
    own = _active(session, assignment_id)
    required = {a['id'] for a in session['assignments'] if a['role_id'] in JUDGING_ROLES}
    initials_complete = len(required) == 3 and required.issubset(session['initials'])
    responses = _record_map(session.get('responses', {}))
    finals = _record_map(session.get('final_positions', {}))
    if not initials_complete:
        phase, phase_outputs, contract = 'initial', ['initial'], _initial_contract()
    elif session.get('status') == 'collecting_responses':
        if assignment_id in responses:
            phase, phase_outputs, contract = 'response_wait', [], {
                'operation': 'response_already_registered',
                'guidance': 'This assignment has completed its only response round.'}
        else:
            phase, phase_outputs, contract = 'response', ['response'], _response_contract()
    elif session.get('status') == 'collecting_final_positions':
        if assignment_id in finals:
            phase, phase_outputs, contract = 'complete', [], {
                'operation': 'final_position_already_registered',
                'guidance': 'This assignment has completed its final position.'}
        else:
            phase, phase_outputs, contract = 'final', ['final_position'], _final_contract()
    else:
        phase, phase_outputs, contract = 'complete', [], {
            'operation': 'final_position_already_registered',
            'guidance': 'The response and final-position rounds are complete.'}
    role = next(r for r in describe_roles('review')['roles'] if r['role_id'] == own['role_id'])
    disclosed_responses = session.get('disclosed_responses', [])
    disclosed_finals = session.get('disclosed_final_positions', [])
    projection = {**session, 'responses': disclosed_responses,
                  'final_positions': disclosed_finals}
    return deepcopy({**store._VERSION, 'session_id': session['id'], 'phase': phase,
        'own_assignment': own, 'phase_allowed_outputs': phase_outputs,
        'input_binding': session['input_binding'],
        'hypothesis_refs': session.get('hypothesis_refs', []),
        'allowed_evidence': session.get('allowed_evidence', []), 'role': role,
        'disclosed_initials': session.get('disclosed_initials', []) if initials_complete else [],
        'disclosed_responses': disclosed_responses,
        'disclosed_final_positions': disclosed_finals,
        'issue_threads': list(build_issue_threads(projection)) if initials_complete else [],
        'output_contract': contract,
        'content_origin': session.get('content_origin'), 'provenance_status': 'declared_only'})


def _issue_contract(*, related_scope: str) -> dict:
    return {'required_fields': sorted(_ISSUE_FIELDS), 'optional_fields': ['related_issue_ids'],
            'id': 'unique nonempty issue ID; prefer an assignment-scoped identifier',
            'raised_by': 'must equal own_assignment.id (the assignment ID), never role_id',
            'target_refs': 'nonempty list of exact {id: string, revision: integer} from hypothesis_refs',
            'evidence_refs': 'unique list of bound artifact ID strings; empty list permitted',
            'question': 'nonempty string in the reviewer own words',
            'impact': 'nonempty string explaining how the issue affects a hypothesis',
            'resolution_condition': 'nonempty string stating what would resolve the issue',
            'related_issue_ids': related_scope, 'severity': ['blocking', 'major', 'minor'],
            'session_id': 'engine-bound; do not include it in submitted issue objects'}


def _initial_contract() -> dict:
    return {'operation': 'register_initial', 'required_fields': sorted(_INITIAL_FIELDS),
            'field_types': {'schema_version': 'integer 1', 'id': 'nonempty string',
                'session_id': 'packet session_id', 'assignment_id': 'own_assignment.id',
                'role_id': 'own_assignment.role_id', 'host_task_id': 'own_assignment.host_task_id',
                'input_binding': 'packet input_binding',
                'rationale': 'nonempty list of nonempty strings',
                'evidence_refs': 'unique list of bound artifact ID strings; empty list permitted',
                'open_issues': 'list; empty list permitted'},
            'open_issues': _issue_contract(related_scope='issues in this same initial only')}


def _response_contract() -> dict:
    return {'operation': 'register_response', 'required_fields': sorted(_RESPONSE_BUNDLE_FIELDS),
            'field_types': {'schema_version': 'integer 1', 'id': 'unique nonempty response bundle ID',
                'session_id': 'packet session_id',
                'assignment_id': 'must equal own_assignment.id, never role_id',
                'role_id': 'own_assignment.role_id', 'host_task_id': 'own_assignment.host_task_id',
                'input_binding': 'packet input_binding',
                'rationale': 'nonempty string required even when both lists are empty',
                'responses': 'list of issue-linked response objects; empty list permitted',
                'new_issues': 'list of new issue objects; empty list permitted'},
            'responses': {'required_fields': sorted(RESPONSE_FIELDS),
                'id': 'unique nonempty response ID', 'issue_id': 'ID of a disclosed initial issue',
                'assignment_id': 'must equal own_assignment.id, never role_id',
                'stance': list(RESPONSE_STANCES), 'rationale': 'nonempty string',
                'evidence_refs': 'unique list of bound artifact ID strings; empty list permitted'},
            'new_issues': _issue_contract(
                related_scope='disclosed initial issue IDs or new issue IDs in this same bundle')}


def _final_contract() -> dict:
    return {'operation': 'register_final_position', 'required_fields': sorted(_FINAL_FIELDS),
            'field_types': {'schema_version': 'integer 1', 'session_id': 'packet session_id',
                'assignment_id': 'must equal own_assignment.id, never role_id',
                'role_id': 'own_assignment.role_id', 'host_task_id': 'own_assignment.host_task_id',
                'input_binding': 'packet input_binding', 'recommendation': 'enum below',
                'change_rationale': 'nonempty string explaining change or why the view is unchanged',
                'issue_dispositions': 'list containing every issue ID exactly once',
                'rationale': 'nonempty string',
                'evidence_refs': 'unique list of bound artifact ID strings; empty list permitted'},
            'recommendation': ['ready', 'ready_with_limits', 'revise', 'defer'],
            'issue_dispositions': {'required_fields': sorted(_DISPOSITION_FIELDS),
                'issue_id': 'one known initial or response issue ID',
                'status': ['resolved', 'open'], 'rationale': 'nonempty string',
                'response_ids': 'unique list of registered response IDs for this issue; empty list permitted',
                'evidence_refs': 'unique list of bound artifact ID strings; empty list permitted'},
            'resolution_rule': ('Every issue requires its raiser final confirmation. A response-round issue also '
                                'requires a resolved disposition from at least one other role.')}


def _validate_initial(payload: dict, session: dict, assignment: dict) -> dict:
    if (type(payload) is not dict or set(payload) != _INITIAL_FIELDS or type(payload['schema_version']) is not int
            or payload['schema_version'] != 1 or not _text(payload['id'])):
        raise ValueError('m1_initial_invalid')
    expected = {'session_id': session['id'], 'assignment_id': assignment['id'],
                'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id'],
                'input_binding': session['input_binding']}
    if any(payload[k] != v for k, v in expected.items()):
        raise ValueError('m1_initial_binding_invalid')
    allowed = {r['id'] for r in session['input_refs']}
    def evidence(value):
        return _strings(value) and len(set(value)) == len(value) and set(value).issubset(allowed)
    if not _strings(payload['rationale'], nonempty=True) or not evidence(payload['evidence_refs']):
        raise ValueError('m1_initial_invalid')
    issues = payload['open_issues']
    if type(issues) is not list:
        raise ValueError('m1_initial_issue_invalid')
    issue_ids = []
    for issue in issues:
        if (type(issue) is not dict or not _ISSUE_FIELDS.issubset(issue)
                or set(issue) - _ISSUE_FIELDS - {'related_issue_ids'}
                or any(not _text(issue[k]) for k in ('id', 'question', 'impact', 'resolution_condition'))
                or issue['raised_by'] != assignment['id'] or issue['severity'] not in ('blocking', 'major', 'minor')
                or not evidence(issue['evidence_refs']) or type(issue['target_refs']) is not list
                or not issue['target_refs']
                or any(type(t) is not dict or set(t) != {'id', 'revision'} or type(t['revision']) is not int
                       or t not in session['hypothesis_refs'] for t in issue['target_refs'])
                or not _strings(issue.get('related_issue_ids', []))):
            raise ValueError('m1_initial_issue_invalid')
        issue_ids.append(issue['id'])
    prior_ids = {i['id'] for p in session['initials'].values() for i in p['open_issues']}
    if len(set(issue_ids)) != len(issue_ids) or set(issue_ids) & prior_ids:
        raise ValueError('m1_initial_issue_invalid')
    if any(set(i.get('related_issue_ids', [])) - set(issue_ids) for i in issues):
        raise ValueError('m1_initial_issue_invalid')
    value = deepcopy(payload)
    for issue in value['open_issues']:
        issue['session_id'] = session['id']
    return {**value, 'provenance_status': 'declared_only'}


def register_initial(root: Path, *, session_id: str, assignment_id: str, payload: dict, command_id: str) -> dict:
    request = _request(command_id, {'operation': 'register_initial', 'session_id': session_id,
                                    'assignment_id': assignment_id, 'payload': payload})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        session = _session(head['state'], session_id)
        assignment = _active(session, assignment_id)
        _current(root, head, session)
        submission_hash = store._hash(store._canonical(request['payload']))
        prior = session['initials'].get(assignment_id)
        if prior is not None:
            if prior['submission_sha256'] != submission_hash:
                raise ValueError('m1_initial_conflict')
            event_type = 'council_initial_replayed'
            objects = {}
        else:
            if session['status'] != 'collecting_initials':
                raise ValueError('m1_council_phase')
            value = _validate_initial(request['payload'], session, assignment)
            if any(value['id'] == p['id'] for p in session['initials'].values()):
                raise ValueError('m1_initial_id_duplicate')
            value['submission_sha256'] = submission_hash
            session['initials'][assignment_id] = value
            if {a['id'] for a in session['assignments']}.issubset(session['initials']):
                session['disclosed_initials'] = [deepcopy(session['initials'][a['id']])
                                                 for a in sorted(session['assignments'], key=lambda a: a['id'])]
                session['status'] = 'collecting_responses'
                _current_attempt(head['state'])['status'] = 'collecting_responses'
            event_type = 'council_initial_registered'
            objects = {f'councils/{session_id}/initials/{submission_hash}.json': store._canonical(value)}
        result = {'session_id': session_id, 'assignment_id': assignment_id,
                  'initial_id': session['initials'][assignment_id]['id'], 'status': session['status'],
                  'submitted_assignment_ids': sorted(session['initials'])}
        return _public_result(_commit(root, head, command_id, request, result, event_type=event_type, objects=objects))


def _evidence_valid(session: dict, value) -> bool:
    allowed = {ref['id'] for ref in session['input_refs']}
    return _strings(value) and len(set(value)) == len(value) and set(value).issubset(allowed)


def _validate_new_issue(issue: dict, *, session: dict, assignment_id: str,
                        related_ids: set[str]) -> dict:
    if (type(issue) is not dict or not _ISSUE_FIELDS.issubset(issue)
            or set(issue) - _ISSUE_FIELDS - {'related_issue_ids'}
            or any(not _text(issue.get(key)) for key in ('id', 'question', 'impact', 'resolution_condition'))
            or issue.get('raised_by') != assignment_id
            or issue.get('severity') not in ('blocking', 'major', 'minor')
            or not _evidence_valid(session, issue.get('evidence_refs'))
            or type(issue.get('target_refs')) is not list or not issue['target_refs']
            or any(type(target) is not dict or set(target) != {'id', 'revision'}
                   or type(target['revision']) is not int or target not in session['hypothesis_refs']
                   for target in issue['target_refs'])
            or not _strings(issue.get('related_issue_ids', []))
            or set(issue.get('related_issue_ids', [])) - related_ids):
        raise ValueError('m1_response_issue_invalid')
    value = deepcopy(issue)
    value['session_id'] = session['id']
    return value


def _validate_response_bundle(payload: dict, session: dict, assignment: dict) -> dict:
    if (type(payload) is not dict or set(payload) != _RESPONSE_BUNDLE_FIELDS
            or type(payload.get('schema_version')) is not int or payload.get('schema_version') != 1
            or not _text(payload.get('id')) or not _text(payload.get('rationale'))
            or type(payload.get('responses')) is not list or type(payload.get('new_issues')) is not list):
        raise ValueError('m1_response_bundle_invalid')
    expected = {'session_id': session['id'], 'assignment_id': assignment['id'],
                'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id'],
                'input_binding': session['input_binding']}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError('m1_response_binding_invalid')
    initial_issue_ids = {issue['id'] for position in session['disclosed_initials']
                         for issue in position['open_issues']}
    assignment_ids = {value['id'] for value in session['assignments']}
    response_ids = []
    response_issue_ids = []
    for response in payload['responses']:
        problems = validate_response(response, issue_ids=initial_issue_ids,
                                     assignment_ids=assignment_ids)
        if any(problem['code'] == 'm1_unknown_issue' for problem in problems):
            raise ValueError('m1_unknown_issue')
        if problems:
            raise ValueError('m1_response_invalid')
        if response['assignment_id'] != assignment['id']:
            raise ValueError('m1_response_binding_invalid')
        if not _evidence_valid(session, response['evidence_refs']):
            raise ValueError('m1_response_evidence_invalid')
        response_ids.append(response['id'])
        response_issue_ids.append(response['issue_id'])
    prior_bundles = _record_map(session.get('responses', {})).values()
    prior_response_ids = {response['id'] for bundle in prior_bundles for response in bundle['responses']}
    if (len(set(response_ids)) != len(response_ids) or len(set(response_issue_ids)) != len(response_issue_ids)
            or set(response_ids) & prior_response_ids):
        raise ValueError('m1_response_id_duplicate')
    new_ids = [issue.get('id') for issue in payload['new_issues']]
    known_ids = {source['issue']['id'] for source in collect_issues(session)}
    if (any(not _text(issue_id) for issue_id in new_ids) or len(set(new_ids)) != len(new_ids)
            or set(new_ids) & known_ids):
        raise ValueError('m1_response_issue_invalid')
    related_ids = initial_issue_ids | set(new_ids)
    value = deepcopy(payload)
    value['new_issues'] = [_validate_new_issue(issue, session=session,
                                                assignment_id=assignment['id'], related_ids=related_ids)
                           for issue in payload['new_issues']]
    return {**value, 'provenance_status': 'declared_only'}


def register_response(root: Path, *, session_id: str, assignment_id: str,
                      payload: dict, command_id: str) -> dict:
    """Register one caller-authored response bundle for an active role."""
    request = _request(command_id, {'operation': 'register_response', 'session_id': session_id,
                                    'assignment_id': assignment_id, 'payload': payload})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        session = _session(head['state'], session_id)
        assignment = _active(session, assignment_id)
        _current(root, head, session)
        responses = _record_map(session.get('responses', {}))
        submission_hash = store._hash(store._canonical(request['payload']))
        prior = responses.get(assignment_id)
        if prior is not None:
            if prior['submission_sha256'] != submission_hash:
                raise ValueError('m1_response_conflict')
            event_type = 'council_response_replayed'
            objects = {}
        else:
            if session['status'] != 'collecting_responses':
                raise ValueError('m1_council_phase')
            value = _validate_response_bundle(request['payload'], session, assignment)
            if any(value['id'] == bundle['id'] for bundle in responses.values()):
                raise ValueError('m1_response_id_duplicate')
            value['submission_sha256'] = submission_hash
            responses[assignment_id] = value
            session['responses'] = responses
            required = {value['id'] for value in session['assignments']}
            if required.issubset(responses):
                session['disclosed_responses'] = [deepcopy(responses[key]) for key in sorted(required)]
                session['status'] = 'collecting_final_positions'
                _current_attempt(head['state'])['status'] = 'collecting_final_positions'
            event_type = 'council_response_registered'
            objects = {f'councils/{session_id}/responses/{submission_hash}.json': store._canonical(value)}
        result = {'session_id': session_id, 'assignment_id': assignment_id,
                  'response_id': responses[assignment_id]['id'], 'status': session['status'],
                  'submitted_assignment_ids': sorted(responses)}
        return _public_result(_commit(root, head, command_id, request, result,
                                     event_type=event_type, objects=objects))


def _validate_final(payload: dict, session: dict, assignment: dict) -> dict:
    if (type(payload) is not dict or set(payload) != _FINAL_FIELDS
            or type(payload.get('schema_version')) is not int or payload.get('schema_version') != 1
            or payload.get('recommendation') not in ('ready', 'ready_with_limits', 'revise', 'defer')
            or not _text(payload.get('change_rationale')) or not _text(payload.get('rationale'))
            or type(payload.get('issue_dispositions')) is not list
            or not _evidence_valid(session, payload.get('evidence_refs'))):
        raise ValueError('m1_final_position_invalid')
    expected = {'session_id': session['id'], 'assignment_id': assignment['id'],
                'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id'],
                'input_binding': session['input_binding']}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError('m1_final_binding_invalid')
    issue_ids = {source['issue']['id'] for source in collect_issues(session)}
    dispositions = payload['issue_dispositions']
    disposition_ids = [value.get('issue_id') if type(value) is dict else None for value in dispositions]
    if (any(type(value) is not dict or set(value) != _DISPOSITION_FIELDS for value in dispositions)
            or any(not _text(issue_id) for issue_id in disposition_ids)
            or len(set(disposition_ids)) != len(dispositions)
            or set(disposition_ids) != issue_ids):
        raise ValueError('m1_final_issue_dispositions_invalid')
    response_to_issue = {response['id']: response['issue_id']
                         for bundle in _record_map(session.get('responses', {})).values()
                         for response in bundle['responses']}
    for value in dispositions:
        if (value['status'] not in ('resolved', 'open') or not _text(value['rationale'])
                or not _strings(value['response_ids'])
                or len(set(value['response_ids'])) != len(value['response_ids'])
                or not _evidence_valid(session, value['evidence_refs'])):
            raise ValueError('m1_final_issue_dispositions_invalid')
        if any(response_to_issue.get(response_id) != value['issue_id'] for response_id in value['response_ids']):
            raise ValueError('m1_final_response_ref_invalid')
    return {**deepcopy(payload), 'provenance_status': 'declared_only'}


def register_final_position(root: Path, *, session_id: str, assignment_id: str,
                            payload: dict, command_id: str) -> dict:
    """Register one caller-authored final position after the response round."""
    request = _request(command_id, {'operation': 'register_final_position', 'session_id': session_id,
                                    'assignment_id': assignment_id, 'payload': payload})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        session = _session(head['state'], session_id)
        assignment = _active(session, assignment_id)
        _current(root, head, session)
        finals = _record_map(session.get('final_positions', {}))
        submission_hash = store._hash(store._canonical(request['payload']))
        prior = finals.get(assignment_id)
        if prior is not None:
            if prior['submission_sha256'] != submission_hash:
                raise ValueError('m1_final_conflict')
            event_type = 'council_final_replayed'
            objects = {}
        else:
            if session['status'] != 'collecting_final_positions':
                raise ValueError('m1_council_phase')
            value = _validate_final(request['payload'], session, assignment)
            value['submission_sha256'] = submission_hash
            finals[assignment_id] = value
            session['final_positions'] = finals
            required = {value['id'] for value in session['assignments']}
            if required.issubset(finals):
                session['disclosed_final_positions'] = [deepcopy(finals[key]) for key in sorted(required)]
                session['status'] = 'final_positions_complete'
                _current_attempt(head['state'])['status'] = 'final_positions_complete'
            event_type = 'council_final_registered'
            objects = {f'councils/{session_id}/finals/{submission_hash}.json': store._canonical(value)}
        result = {'session_id': session_id, 'assignment_id': assignment_id,
                  'status': session['status'], 'submitted_assignment_ids': sorted(finals)}
        return _public_result(_commit(root, head, command_id, request, result,
                                     event_type=event_type, objects=objects))


def replace_assignment(root: Path, *, session_id: str, assignment_id: str, replacement: dict,
                       reason: str, command_id: str) -> dict:
    request = _request(command_id, {'operation': 'replace_assignment', 'session_id': session_id,
        'assignment_id': assignment_id, 'replacement': replacement, 'reason': reason})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return _public_result(replay)
        head = store.read_head(root)
        session = _session(head['state'], session_id)
        _current(root, head, session)
        if session['status'] != 'collecting_initials':
            raise ValueError('m1_council_phase')
        old = _active(session, assignment_id)
        replacement = request['replacement']
        if (not _text(reason) or type(replacement) is not dict or set(replacement) != ASSIGNMENT_INPUT_FIELDS
                or replacement['role_id'] != old['role_id']):
            raise ValueError('m1_assignment_replacement_invalid')
        used = session['assignments'] + [h['assignment'] for h in session['assignment_history']]
        if any(replacement['id'] == a['id'] or replacement['host_task_id'] == a['host_task_id'] for a in used):
            raise ValueError('m1_assignment_replacement_reused')
        raw = [{k: a[k] for k in ASSIGNMENT_INPUT_FIELDS} if a['id'] != assignment_id else replacement
               for a in session['assignments']]
        bound = bind_assignments(raw, session_id=session_id, input_binding=session['input_binding'],
            author_assignment_ids=set(session['author_assignment_ids']),
            author_host_task_ids=set(session['author_host_task_ids']))
        session['assignment_history'].append({'assignment': deepcopy(old), 'status': 'failed_replaced',
            'reason': reason, 'initial': session['initials'].pop(assignment_id, None),
            'replacement_assignment_id': replacement['id'], 'provenance_status': 'declared_only'})
        session['assignments'] = bound
        result = {'session_id': session_id, 'assignment': deepcopy(_active(session, replacement['id'])),
                  'replaced_assignment_id': assignment_id, 'status': session['status']}
        return _public_result(_commit(root, head, command_id, request, result,
            event_type='council_assignment_replaced', objects={}))


def read_reviewer_packet(root: Path, *, session_id: str, assignment_id: str) -> dict:
    """Read a current, validated reviewer packet without writing any receipt."""
    head = store.read_head(root)
    session = _session(head['state'], session_id)
    _current(root, head, session)
    return reviewer_packet(session, assignment_id)


def resume_council(root: Path, head: dict) -> dict:
    """Narrow review resume: session lifecycle replaces an authoring packet."""
    attempt = _current_attempt(head['state'])
    session = _session(head['state'], attempt['session_id'])
    reasons = []
    actions = {'collecting_initials': 'collect_initials',
               'collecting_responses': 'collect_responses',
               'collecting_final_positions': 'collect_final_positions',
               'final_positions_complete': 'await_decision_engine'}
    action = actions.get(session['status'], 'await_user')
    try:
        _current(root, head, session)
    except ValueError as exc:
        action = 'await_user'
        reasons = [str(exc)]
    if action == 'await_decision_engine':
        reasons = ['All final positions are recorded; a later decision engine must evaluate progression.']
    return {**store._VERSION, 'head_id': head['id'], 'current_node_id': 'review',
            'status': session['status'], 'action': action, 'wait_reasons': reasons,
            'session_id': session['id'], 'current_attempt': deepcopy(attempt),
            'inputs': {'objects': deepcopy(session['input_refs']), 'input_binding': session['input_binding']},
            'submitted_assignment_ids': sorted(session['initials']),
            'pending_assignment_ids': sorted(a['id'] for a in session['assignments'] if a['id'] not in session['initials']),
            'response_assignment_ids': sorted(_record_map(session.get('responses', {}))),
            'final_position_assignment_ids': sorted(_record_map(session.get('final_positions', {}))),
            'content_origin': session['content_origin']}


def redact_pending_councils(value: dict) -> dict:
    """CLI projection: hide pending initial bodies, including historical events.

    Raw immutable store receipts remain available to trusted local code. This
    projection is a presentation boundary, not host filesystem authorization.
    """
    if 'receipt' in value:
        value = {**value, 'receipt': redact_pending_councils(value['receipt'])}
    sessions = value.get('state', {}).get('sessions', {})
    hidden = {s['id'] for s in sessions.values() if s['status'] == 'collecting_initials'}
    if not hidden:
        return value
    def redact(item):
        if type(item) is list:
            return [redact(v) for v in item]
        if type(item) is not dict:
            return item
        result = {k: redact(v) for k, v in item.items()}
        if item.get('id') in hidden and 'initials' in item:
            result['submitted_assignment_ids'] = sorted(item['initials'])
            result['initials'] = {}
            result['disclosed_initials'] = []
            for history in result.get('assignment_history', []):
                history['initial'] = None
        if item.get('operation') == 'register_initial' and item.get('session_id') in hidden:
            result['payload'] = {'redacted': True}
        return result
    return redact(value)
