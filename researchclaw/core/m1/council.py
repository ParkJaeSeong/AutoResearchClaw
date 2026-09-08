"""Independent initial collection, frozen disclosure and declared role replacement.

This is packet isolation, not a sandbox against a host reading the store. The
engine records caller declarations only; native execution observations belong in
separate host evidence. No response, final position, decision or runner exists.
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
from .packets import _commit, _current_attempt, _mutation, _replay, _request
from .roles import describe_roles

_HYPOTHESIS = 'hypotheses/hypotheses.json'
_INPUT_PATHS = (*CORPUS_PATHS, 'knowledge/extractions.jsonl', 'knowledge/extraction_manifest.json',
                'knowledge/synthesis.json', 'knowledge/synthesis.md', _HYPOTHESIS, 'hypotheses/hypotheses.md')
_INITIAL_FIELDS = {'schema_version', 'id', 'session_id', 'assignment_id', 'role_id', 'host_task_id',
                   'input_binding', 'rationale', 'evidence_refs', 'open_issues'}
_ISSUE_FIELDS = {'id', 'raised_by', 'target_refs', 'evidence_refs', 'question', 'impact',
                 'severity', 'resolution_condition'}


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
            'initials': {}, 'responses': [], 'final_positions': [], 'disclosed_initials': [],
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
    complete = len(required) == 3 and required.issubset(session['initials'])
    phase = 'response' if complete else 'initial'
    role = next(r for r in describe_roles('review')['roles'] if r['role_id'] == own['role_id'])
    return deepcopy({**store._VERSION, 'session_id': session['id'], 'phase': phase,
        'own_assignment': own, 'input_binding': session['input_binding'],
        'hypothesis_refs': session.get('hypothesis_refs', []),
        'allowed_evidence': session.get('allowed_evidence', []), 'role': role,
        'disclosed_initials': session.get('disclosed_initials', []) if complete else [],
        'output_contract': {'operation': 'register_initial' if not complete else 'response_engine_unavailable',
            'required_fields': sorted(_INITIAL_FIELDS), 'rationale': 'nonempty list of nonempty strings',
            'evidence_refs': 'unique bound artifact ID strings; empty permitted',
            'open_issues': {'required_fields': sorted(_ISSUE_FIELDS), 'optional_fields': ['related_issue_ids'],
                'id': 'unique issue ID; prefer an assignment-scoped identifier',
                'raised_by': 'must equal own_assignment.id, not role_id',
                'target_refs': 'nonempty list of exact {id, revision} from hypothesis_refs',
                'evidence_refs': 'unique bound artifact ID strings; empty permitted',
                'question': 'nonempty unresolved question in the reviewer own words',
                'impact': 'nonempty explanation of how the issue affects the hypothesis',
                'resolution_condition': 'nonempty condition that would resolve the issue',
                'related_issue_ids': 'optional list referring only to issues in this same initial',
                'severity': ['blocking', 'major', 'minor'], 'session_id': 'engine-bound',
                'empty_permitted': True}},
        'content_origin': session.get('content_origin'), 'provenance_status': 'declared_only'})


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
    action = 'collect_initials' if session['status'] == 'collecting_initials' else 'await_response_engine'
    try:
        _current(root, head, session)
    except ValueError as exc:
        action = 'await_user'
        reasons = [str(exc)]
    if action == 'await_response_engine':
        reasons = ['All initial positions are disclosed; response registration belongs to Task 11.']
    return {**store._VERSION, 'head_id': head['id'], 'current_node_id': 'review',
            'status': session['status'], 'action': action, 'wait_reasons': reasons,
            'session_id': session['id'], 'current_attempt': deepcopy(attempt),
            'inputs': {'objects': deepcopy(session['input_refs']), 'input_binding': session['input_binding']},
            'submitted_assignment_ids': sorted(session['initials']),
            'pending_assignment_ids': sorted(a['id'] for a in session['assignments'] if a['id'] not in session['initials']),
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
