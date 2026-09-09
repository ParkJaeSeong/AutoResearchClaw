"""Node-neutral council planners and reviewer-only disclosure projections.

Raw snapshots are trusted orchestrator inputs. Projection privacy is not host or
filesystem isolation; reviewer identities remain declared responsibility.
"""
from copy import deepcopy
import json

from . import store
from .contracts import _COMMON, _check, validate_record
from .dependencies import _References, _node
from .issues import _Inputs, _require
from .positions import validate_position_change

_COUNCIL_FIELDS = set(_COMMON) | {'session_id', 'milestone', 'node', 'attempt',
    'author_assignment_ids', 'required_roles', 'allowed_evidence_refs', 'issue_ids'}
_SUBMISSION_FIELDS = set(_COMMON) | {'session_id', 'assignment_id', 'input_binding', 'phase',
    'rationale', 'evidence_refs', 'positions', 'retained_position_refs', 'response_refs',
    'issue_proposals', 'recommendation', 'host_id', 'model_id'}
_ASSIGNMENT_FIELDS = {'id', 'project_id', 'actor_id', 'role', 'milestone', 'active'}
_SESSION_FIELDS = {'id', 'project_id', 'input_binding', 'participant_assignment_ids', 'frozen'}
_COLLECTIONS = {'councils', 'council_submissions', 'assignments', 'review_sessions',
                'issues', 'positions', 'position_acknowledgements'}
_PHASES = ('initial', 'response', 'final')
_REF_FIELDS = {'project_id', 'head_id', 'artifact_id', 'sha256'}


def _valid(spec, value):
    errors = []
    _check(spec, value, '$', errors)
    return not errors


def _common(value, fields, project):
    return (type(value) is dict and set(value) == fields
            and _valid(_COMMON, {key: value[key] for key in _COMMON})
            and value['project_id'] == project
            and (value['provenance_status'] != 'host_observed' or bool(value['observation_refs'])))


def _ids(value, *, nonempty=False):
    return (_valid(('array', 'uuid'), value) and (bool(value) or not nonempty)
            and len(value) == len(set(value)))


def _context(snapshot):
    inputs = _Inputs(snapshot)
    _require(all(type(record['state'].get(name, {})) is dict
                 for _, record in inputs.history for name in _COLLECTIONS), 'council_collection_invalid')
    return inputs


def _fresh_ids(inputs, identities, *, reusable=()):
    existing = set()
    for _, record in inputs.history:
        existing.update(record['object_inputs'])
        for collection in record['state'].values():
            if type(collection) is dict:
                existing.update(item['id'] for item in collection.values()
                                if type(item) is dict and type(item.get('id')) is str)
    _require(len(identities) == len(set(identities))
             and not (set(identities) - set(reusable)) & existing, 'council_identity_exists')


def _record_ref(inputs, collection, record):
    head = next(head for head, historical in inputs.history
                if historical['state'].get(collection, {}).get(record['id']) == record)
    return dict(project_id=inputs.project, head_id=head, artifact_id=record['id'],
                sha256=store._hash(store._canonical(record)))


def _session(inputs, council):
    session = inputs.registered('review_sessions', council['session_id'])
    _require(set(session) == _SESSION_FIELDS and session['frozen'] is True
             and _ids(session['participant_assignment_ids'], nonempty=True), 'council_session_invalid')
    return session


def _shared_issues(inputs, council):
    prepared = next(((head, record) for head, record in inputs.history
                     if record['state'].get('councils', {}).get(council['id']) == council), inputs.history[-1])
    result = []
    for identity in council['issue_ids']:
        issue = prepared[1]['state'].get('issues', {}).get(identity)
        _require(type(issue) is dict, 'council_issue_invalid')
        ref = dict(project_id=inputs.project, head_id=prepared[0], artifact_id=identity,
                   sha256=store._hash(store._canonical(issue)))
        inputs.reference(ref, 'issues', 'Issue')
        result.append(dict(issue_ref=ref, issue=issue))
    return result


def _submissions(inputs, council):
    records = {phase: {} for phase in _PHASES}
    participants = set(_session(inputs, council)['participant_assignment_ids'])
    for identity in inputs.state.get('council_submissions', {}):
        record = inputs.registered('council_submissions', identity)
        _require(_common(record, _SUBMISSION_FIELDS, inputs.project), 'council_submission_invalid')
        if record['session_id'] != council['session_id']:
            continue
        phase, actor = record['phase'], record['assignment_id']
        _require(phase in _PHASES and actor in participants and actor not in records[phase], 'council_submission_invalid')
        records[phase][actor] = record
    return records


def _phase(inputs, council, records):
    required = set(_session(inputs, council)['participant_assignment_ids'])
    return next((phase for phase in _PHASES if set(records[phase]) != required), 'complete')


def _private(inputs):
    """All undisclosed body identities, including embedded proposal bytes."""
    private_ids, private_hashes = set(), set()
    for identity in inputs.state.get('councils', {}):
        council = inputs.registered('councils', identity)
        records = _submissions(inputs, council)
        required = set(_session(inputs, council)['participant_assignment_ids'])
        for phase in _PHASES:
            if set(records[phase]) == required:
                continue
            for submission in records[phase].values():
                for body in [submission, *submission['positions'], *submission['issue_proposals']]:
                    private_ids.add(body['id'])
                    private_hashes.add(store._hash(store._canonical(body)))
    return private_ids, private_hashes


def _graph(inputs, roots, *, issue_leaves=()):
    resolver = _References(inputs)
    private_ids, private_hashes = _private(inputs)
    allowed, pending = {}, list(roots)
    leaves = {_node(ref) for ref in issue_leaves}
    while pending:
        ref = pending.pop()
        _require(resolver.resolve(ref), 'council_input_stale')
        _require(ref['artifact_id'] not in private_ids and ref['sha256'] not in private_hashes,
                 'council_private_input')
        key = _node(ref)
        if key in allowed:
            continue
        allowed[key] = ref
        if key in leaves:
            # Frozen Issue context is not a current-source dependency. Preserve
            # its exact historical target metadata without granting byte access.
            issue = inputs.reference(ref, 'issues', 'Issue')
            for source in [*issue['target_refs'], *issue['observation_refs']]:
                _require(source['artifact_id'] not in private_ids and source['sha256'] not in private_hashes,
                         'council_private_input')
            continue
        try:
            value = json.loads(inputs.objects[ref['sha256']])
        except (UnicodeDecodeError, ValueError):
            continue
        queue = [value]
        while queue:
            item = queue.pop()
            if type(item) is dict:
                if set(item) == _REF_FIELDS:
                    pending.append(item)
                else:
                    queue.extend(item.values())
            elif type(item) is list:
                queue.extend(item)
    return allowed


def _council_for(inputs, assignment_id):
    _require(_valid('uuid', assignment_id), 'council_assignment_invalid')
    matches = [inputs.registered('councils', identity) for identity, council in inputs.state.get('councils', {}).items()
               if assignment_id in council.get('required_roles', {}).values()]
    _require(len(matches) == 1, 'council_assignment_invalid')
    actor = inputs.assignment(assignment_id)
    _require(actor['role'] == 'resolver', 'council_assignment_invalid')
    return matches[0], actor


def _disclosed(inputs, council, records):
    required = set(_session(inputs, council)['participant_assignment_ids'])
    result = {phase: [] for phase in _PHASES}
    for phase in _PHASES:
        if set(records[phase]) != required:
            break
        result[phase] = [dict(submission_ref=_record_ref(inputs, 'council_submissions', record), submission=record)
                         for _, record in sorted(records[phase].items())]
    return result


def reviewer_packet(snapshot: dict, assignment_id: str) -> dict:
    """Whitelist only selected-reviewer inputs and phase-permitted disclosures."""
    inputs = _context(snapshot)
    council, actor = _council_for(inputs, assignment_id)
    session = _session(inputs, council)
    shared_issues = _shared_issues(inputs, council)
    shared = _graph(inputs, [session['input_binding'], *council['allowed_evidence_refs'],
                             *(item['issue_ref'] for item in shared_issues)],
                    issue_leaves=[item['issue_ref'] for item in shared_issues])
    records = _submissions(inputs, council)
    phase = _phase(inputs, council, records)
    disclosed = _disclosed(inputs, council, records)
    own = [dict(submission_ref=_record_ref(inputs, 'council_submissions', records[p][assignment_id]),
                submission=records[p][assignment_id]) for p in _PHASES if assignment_id in records[p]]
    waiting = phase != 'complete' and assignment_id in records[phase]
    return deepcopy({**store._VERSION, 'session_id': session['id'],
        'milestone': council['milestone'], 'node': council['node'], 'attempt': council['attempt'],
        'phase': f'{phase}_wait' if waiting else phase, 'own_assignment': actor,
        'input_binding': session['input_binding'], 'allowed_evidence_refs': list(shared.values()),
        'shared_issues': shared_issues,
        'own_submissions': own, 'disclosed_initials': disclosed['initial'],
        'disclosed_responses': disclosed['response'], 'disclosed_finals': disclosed['final'],
        'output_contract': {'operation': 'council.submit', 'allowed_phase': None if waiting or phase == 'complete' else phase,
                            'submission_fields': sorted(_SUBMISSION_FIELDS)},
        'isolation_level': 'instructions_only', 'identity_provenance': 'declared_only',
        'content_origin': council['content_origin']})


def prepare_council(snapshot: dict, payload: dict) -> dict:
    """Create only the bounded council, assignments and frozen A06 session."""
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'assignments', 'review_session', 'council'}, 'council_prepare_invalid')
    council, session, assignments = deepcopy(payload['council']), deepcopy(payload['review_session']), deepcopy(payload['assignments'])
    _require(_common(council, _COUNCIL_FIELDS, inputs.project)
             and _valid('uuid', council['session_id']) and _valid('uuid', council['attempt'])
             and council['milestone'] in ('M1', 'M2', 'M3') and _valid('text', council['node'])
             and _ids(council['author_assignment_ids'], nonempty=True) and _ids(council['issue_ids'])
             and type(council['allowed_evidence_refs']) is list, 'council_prepare_invalid')
    _require(type(session) is dict and set(session) == _SESSION_FIELDS and session['id'] == council['session_id']
             and session['project_id'] == inputs.project and session['frozen'] is True
             and _ids(session['participant_assignment_ids'], nonempty=True), 'council_session_invalid')
    roles = council['required_roles']
    _require(type(roles) is dict and bool(roles) and all(_valid('text', role) for role in roles)
             and _ids(list(roles.values()), nonempty=True)
             and set(roles.values()) == set(session['participant_assignment_ids']), 'council_assignment_invalid')
    _require(council['id'] not in inputs.state.get('councils', {})
             and session['id'] not in inputs.state.get('review_sessions', {}), 'council_exists')
    _require(type(assignments) is list, 'council_assignment_invalid')
    by_id = {}
    for actor in assignments:
        _require(type(actor) is dict and set(actor) == _ASSIGNMENT_FIELDS
                 and _valid('uuid', actor['id']) and actor['project_id'] == inputs.project
                 and _valid('text', actor['actor_id']) and actor['active'] is True
                 and actor['milestone'] == council['milestone'] and actor['role'] in ('owner', 'resolver')
                 and actor['id'] not in by_id, 'council_assignment_invalid')
        if actor['id'] in inputs.state.get('assignments', {}):
            _require(actor['id'] in council['author_assignment_ids']
                     and inputs.registered('assignments', actor['id']) == actor, 'council_assignment_invalid')
        by_id[actor['id']] = actor
    reviewers, authors = set(roles.values()), set(council['author_assignment_ids'])
    _require(set(by_id) == reviewers | authors and not reviewers & authors
             and all(by_id[i]['role'] == 'owner' for i in authors)
             and all(by_id[i]['role'] == 'resolver' for i in reviewers)
             and len({by_id[i]['actor_id'] for i in reviewers}) == len(reviewers)
             and not {by_id[i]['actor_id'] for i in reviewers} & {by_id[i]['actor_id'] for i in authors}, 'council_assignment_invalid')
    _fresh_ids(inputs, [council['id'], session['id'], *by_id],
               reusable=authors & set(inputs.state.get('assignments', {})))
    shared_issues = _shared_issues(inputs, council)
    _graph(inputs, [session['input_binding'], *council['allowed_evidence_refs'], *council['observation_refs'],
                    *(item['issue_ref'] for item in shared_issues)],
           issue_leaves=[item['issue_ref'] for item in shared_issues])
    for identity in council['issue_ids']:
        inputs.registered('issues', identity, 'Issue')
    objects = {record['id']: store._canonical(record) for record in [council, session, *assignments]}
    return {'state_patch': {'councils': {**inputs.state.get('councils', {}), council['id']: council},
                           'review_sessions': {**inputs.state.get('review_sessions', {}), session['id']: session},
                           'assignments': {**inputs.state.get('assignments', {}), **by_id}},
            'event': {**store._VERSION, 'type': 'council_prepared', 'payload': {'council_id': council['id'], 'session_id': session['id']}},
            'object_inputs': objects}


def register_submission(snapshot: dict, payload: dict) -> dict:
    """Plan one actor's phase submission; no issue publication or resolution."""
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'submission'}, 'council_submission_invalid')
    submission = deepcopy(payload['submission'])
    _require(_common(submission, _SUBMISSION_FIELDS, inputs.project), 'council_submission_invalid')
    council, actor = _council_for(inputs, submission['assignment_id'])
    session = _session(inputs, council)
    _require(submission['session_id'] == session['id'] and submission['input_binding'] == session['input_binding']
             and submission['producer_id'] == actor['actor_id'], 'council_submission_binding_invalid')
    records = _submissions(inputs, council)
    phase = _phase(inputs, council, records)
    _require(submission['phase'] == phase and phase in _PHASES
             and actor['id'] not in records[phase], 'council_phase_invalid')
    _require(submission['id'] not in inputs.state.get('council_submissions', {})
             and all(s['event_id'] != submission['event_id'] for s in inputs.state.get('council_submissions', {}).values()), 'council_submission_exists')
    _require(all(_valid('text', submission[k]) for k in ('rationale', 'host_id', 'model_id'))
             and all(type(submission[k]) is list for k in ('evidence_refs', 'positions', 'retained_position_refs', 'response_refs', 'issue_proposals')),
             'council_submission_invalid')
    _require(submission['recommendation'] in ('ready', 'ready_with_limits', 'revise', 'defer') if phase == 'final'
             else submission['recommendation'] is None, 'council_recommendation_invalid')
    disclosed = _disclosed(inputs, council, records)
    shared_issues = _shared_issues(inputs, council)
    allowed = _graph(inputs, [session['input_binding'], *council['allowed_evidence_refs'],
                             *(item['issue_ref'] for item in shared_issues)],
                     issue_leaves=[item['issue_ref'] for item in shared_issues])
    prior_items = [item for p in _PHASES[:_PHASES.index(phase)] for item in disclosed[p]]
    disclosed_refs = {_node(item['submission_ref']) for item in prior_items}
    allowed.update({_node(item['submission_ref']): item['submission_ref'] for item in prior_items})
    for item in prior_items:
        for position in item['submission']['positions']:
            ref = _record_ref(inputs, 'positions', position)
            allowed[_node(ref)] = ref
    resolver = _References(inputs)

    def evidence(ref):
        _require(resolver.resolve(ref) and _node(ref) in allowed, 'council_evidence_not_allowed')

    for ref in [*submission['evidence_refs'], *submission['observation_refs']]:
        evidence(ref)
    for ref in submission['response_refs']:
        inputs.reference(ref, 'council_submissions')
        _require(_node(ref) in disclosed_refs, 'council_response_not_disclosed')
    known_proposals = {p['id']: p for item in prior_items for p in item['submission']['issue_proposals']}
    known_issues = set(council['issue_ids']) | {identity for identity, proposal in known_proposals.items()
        if inputs.state.get('issues', {}).get(identity) == proposal}
    own_positions = {}
    for p in _PHASES[:_PHASES.index(phase)]:
        own = records[p].get(actor['id'])
        if own:
            for position in own['positions']:
                own_positions[position['issue_id']] = position
    retained, new_positions, covered = [], {}, set()
    for ref in submission['retained_position_refs']:
        position = inputs.reference(ref, 'positions', 'Position')
        _require(phase != 'initial' and own_positions.get(position['issue_id']) == position
                 and position['issue_id'] not in covered, 'council_position_invalid')
        covered.add(position['issue_id']); retained.append(position)
    event_ids = set()
    for position in submission['positions']:
        _require(not validate_position_change(snapshot, position)
                 and position['assignment_id'] == actor['id'] and position['session_id'] == session['id']
                 and position['issue_id'] in known_issues and position['issue_id'] not in covered
                 and position['id'] not in new_positions and position['event_id'] not in event_ids, 'council_position_invalid')
        previous = own_positions.get(position['issue_id'])
        if previous:
            _require(position['changed_from'] is not None
                     and inputs.reference(position['changed_from'], 'positions', 'Position') == previous, 'council_position_invalid')
        else:
            _require(position['changed_from'] is None, 'council_position_invalid')
        for ref in [*position['evidence_refs'], *position['observation_refs']]:
            evidence(ref)
        new_positions[position['id']] = position
        event_ids.add(position['event_id']); covered.add(position['issue_id'])
    _require(phase != 'final' or not submission['issue_proposals'], 'council_proposal_invalid')
    existing_proposals = {p['id'] for s in inputs.state.get('council_submissions', {}).values() for p in s['issue_proposals']}
    proposal_ids = set()
    for proposal in submission['issue_proposals']:
        _require(not validate_record('Issue', proposal) and proposal['project_id'] == inputs.project
                 and proposal['producer_id'] == actor['actor_id'] and proposal['origin']['milestone'] == council['milestone']
                 and proposal['origin']['node'] == council['node'] and proposal['origin']['attempt'] == council['attempt']
                 and proposal['id'] not in existing_proposals | proposal_ids | set(inputs.state.get('issues', {})), 'council_proposal_invalid')
        if proposal['owner_assignment_id'] is not None:
            _require(inputs.assignment(proposal['owner_assignment_id'])['role'] == 'owner', 'council_proposal_invalid')
        for ref in [*proposal['target_refs'], *proposal['observation_refs']]:
            evidence(ref)
        proposal_ids.add(proposal['id'])
    _fresh_ids(inputs, [submission['id'], *new_positions, *proposal_ids])
    objects = {record['id']: store._canonical(record) for record in [submission, *new_positions.values()]}
    return {'state_patch': {'council_submissions': {**inputs.state.get('council_submissions', {}), submission['id']: submission},
                           'positions': {**inputs.state.get('positions', {}), **new_positions}},
            'event': {**store._VERSION, 'type': 'council_submission_registered',
                      'payload': {'submission_id': submission['id'], 'session_id': session['id'], 'phase': phase}},
            'object_inputs': objects}


def public_result(snapshot, operation, payload):
    """Sanitize both first and replay receipts at the exact committed ancestor."""
    envelope = {**store._VERSION, 'id': snapshot['id']}
    if operation == 'council.submit':
        return {**envelope, 'packet': reviewer_packet(snapshot, payload['submission']['assignment_id'])}
    inputs = _context(snapshot)
    council = inputs.registered('councils', payload['council']['id'])
    return {**envelope, 'council': {'id': council['id'], 'session_id': council['session_id'],
        'phase': _phase(inputs, council, _submissions(inputs, council)),
        'participant_count': len(council['required_roles']), 'isolation_level': 'instructions_only'}}
