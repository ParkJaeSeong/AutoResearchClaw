"""Pure append-only issue policy. Trusted ancestry is supplied only by commands.

Prerequisite creation is outside A04; see issue-policy-inputs.md. This checks
recorded policy/evidence linkage, not scientific truth or host authentication.
"""
from copy import deepcopy
import json
from .contracts import validate_record
from . import store

_TRANSITIONS = {None: {'open'}, 'open': {'checking', 'deferred', 'transferred', 'superseded'},
    'checking': {'resolved', 'open'}, 'deferred': {'checking'}, 'transferred': {'checking'},
    'resolved': {'reopened'}, 'reopened': {'checking'}, 'superseded': set()}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _evidence_content(data):
    """Compare bytes/content, not a fresh research-graph identity envelope."""
    try:
        value = json.loads(data)
        if (type(value) is dict and value.get('workflow_version') == store._VERSION['workflow_version']
                and value.get('schema_version') == 1):
            envelope = {'schema_version', 'workflow_version', 'project_id', 'id', 'event_id',
                        'producer_id', 'content_origin', 'provenance_status', 'observation_refs'}
            return store._canonical({key: item for key, item in value.items() if key not in envelope})
    except (ValueError, UnicodeDecodeError):
        pass
    return data


class _Inputs:
    def __init__(self, snapshot):
        self.state = snapshot['state']
        self.project = self.state['project_id']
        context = snapshot.get('_issue_context', {})
        self.history = context.get('history', [])
        self.objects = context.get('objects', {})
        _require(self.history and self.history[-1][0] == snapshot['id']
                 and self.history[-1][1]['state'] == self.state, 'issue_context_missing')
        self.heads = {head: record for head, record in self.history}

    def registered(self, collection, identity, kind=None):
        record = self.state.get(collection, {}).get(identity)
        _require(type(record) is dict and record.get('id') == identity
                 and record.get('project_id') == self.project, 'issue_prerequisite_missing')
        digest = store._hash(store._canonical(record))
        _require(self.objects.get(digest) == store._canonical(record)
                 and digest in self.history[-1][1]['objects'], 'issue_prerequisite_unbacked')
        if kind:
            _require(not validate_record(kind, record), 'issue_record_invalid')
        return record

    def assignment(self, identity):
        record = self.registered('assignments', identity)
        _require(set(record) == {'id', 'project_id', 'actor_id', 'role', 'milestone', 'active'}
                 and type(record['actor_id']) is str and bool(record['actor_id'].strip())
                 and record['role'] in ('owner', 'resolver') and record['milestone'] in ('M1', 'M2', 'M3')
                 and record['active'] is True, 'issue_assignment_invalid')
        return record

    def reference(self, ref, collection=None, kind=None):
        _require(type(ref) is dict and set(ref) == {'project_id', 'head_id', 'artifact_id', 'sha256'}
                 and ref['project_id'] == self.project and ref['head_id'] in self.heads,
                 'issue_reference_invalid')
        ancestor = self.heads[ref['head_id']]
        data = self.objects.get(ref['sha256'])
        _require(data is not None and store._hash(data) == ref['sha256']
                 and ref['sha256'] in ancestor['objects'], 'issue_reference_invalid')
        if collection:
            record = ancestor['state'].get(collection, {}).get(ref['artifact_id'])
            _require(type(record) is dict and store._canonical(record) == data,
                     'issue_reference_invalid')
            _require(self.state.get(collection, {}).get(ref['artifact_id']) == record,
                     'issue_reference_stale')
            return self.registered(collection, ref['artifact_id'], kind)
        # General evidence may be raw bytes. Logical names must bind to those
        # bytes at the named ancestor and remain current, not merely exist.
        aliases, at_ref = {}, None
        for head, record in self.history:
            aliases.update(record['object_inputs'])
            if head == ref['head_id']:
                at_ref = dict(aliases)
        _require(at_ref.get(ref['artifact_id']) == ref['sha256'], 'issue_reference_invalid')
        _require(aliases.get(ref['artifact_id']) == ref['sha256'], 'issue_reference_stale')
        return data

    def verification(self, identity, issue_id):
        record = self.registered('verifications', identity, 'Verification')
        _require(issue_id in record['issue_ids'], 'verification_issue_mismatch')
        _require(record['acceptance_rule'] == self.state['issues'][issue_id]['resolution_condition'],
                 'verification_binding_mismatch')
        self.assignment(record['owner_assignment_id'])
        for ref in [record['budget_ref'], *record['input_refs'], *record['observation_refs']]:
            self.reference(ref)
        return record


def propose_issue_event(snapshot: dict, payload: dict) -> dict:
    """Return an immutable-object transition plan; never reads/writes files."""
    _require(type(payload) is dict and set(payload) == {'issue', 'event'}, 'issue_payload_invalid')
    event, new_issue = deepcopy(payload['event']), deepcopy(payload['issue'])
    _require(not validate_record('IssueEvent', event), 'issue_record_invalid')
    inputs = _Inputs(snapshot)
    state, project = inputs.state, inputs.project
    _require(event['project_id'] == project, 'issue_project_mismatch')
    actor = inputs.assignment(event['actor_assignment_id'])
    _require(event['producer_id'] == actor['actor_id'], 'issue_actor_mismatch')
    events = state.get('issue_events', [])
    _require(type(events) is list, 'issue_history_invalid')
    _require(all(e['id'] != event['id'] and e['event_id'] != event['event_id'] for e in events), 'issue_event_exists')
    issues = state.get('issues', {})
    issue = issues.get(event['issue_id'])
    if new_issue is not None:
        _require(issue is None, 'issue_already_exists')
        _require(not validate_record('Issue', new_issue), 'issue_record_invalid')
        _require(new_issue['id'] == event['issue_id'] and new_issue['project_id'] == project, 'issue_project_mismatch')
        _require(new_issue['producer_id'] == actor['actor_id'], 'issue_actor_mismatch')
        issue = new_issue
    else:
        _require(issue is not None, 'issue_missing')
    prior = [e for e in events if e['issue_id'] == issue['id']]
    imported = issue['id'] in state.get('imported_issue_states', {})
    _require(new_issue is not None or prior or imported, 'issue_history_invalid')
    current = prior[-1]['to_status'] if prior else ('open' if imported else None)
    _require(event['from_status'] == current, 'issue_from_status_mismatch')
    target = event['to_status']
    if target == 'resolved':
        _require(bool(event['verification_refs']), 'resolution_evidence_missing')
    _require(target in _TRANSITIONS[current], 'issue_transition_invalid')
    _require(not event['successor_ids'] or target == 'superseded', 'issue_payload_invalid')
    transfer_fields = {'to_milestone', 'owner_assignment_id', 'verification_id', 'acceptance_event_id'}
    allowed = transfer_fields if target == 'transferred' else ({'owner_assignment_id'} if target == 'checking' else set())
    _require(not (set(event) & transfer_fields) - allowed, 'issue_payload_invalid')
    owner_id = issue['owner_assignment_id']
    for previous in prior:
        owner_id = previous.get('owner_assignment_id', owner_id)
    if new_issue:
        _require(owner_id is not None, 'issue_owner_required')
        inputs.assignment(owner_id)
        for ref in [*issue['target_refs'], *issue['observation_refs']]:
            inputs.reference(ref)
    for ref in event['observation_refs']:
        inputs.reference(ref)
    if target == 'checking':
        owner_id = event.get('owner_assignment_id', owner_id)
        _require(owner_id is not None, 'issue_owner_required')
        owner = inputs.assignment(owner_id)
        _require(owner['role'] == 'owner', 'issue_assignment_invalid')
        _require(bool(event['verification_refs']), 'verification_evidence_missing')
        for ref in event['verification_refs']:
            v = inputs.reference(ref, 'verifications', 'Verification')
            v = inputs.verification(v['id'], issue['id'])
            _require(v['owner_assignment_id'] == owner_id, 'verification_owner_mismatch')
    elif target in ('resolved', 'reopened'):
        _require(bool(event['verification_refs']), 'new_conflict_required')
        checking = next((e for e in reversed(prior) if e['to_status'] == 'checking'), None)
        _require(checking is not None and owner_id is not None, 'verification_evidence_missing')
        owner = inputs.assignment(owner_id)
        if target == 'resolved':
            _require(actor['role'] == 'resolver' and actor['actor_id'] not in
                     {owner['actor_id'], issue['producer_id']}, 'independent_resolver_required')
        for ref in event['verification_refs']:
            result = inputs.reference(ref, 'verification_results', 'VerificationResult')
            v = inputs.verification(result['verification_id'], issue['id'])
            bound = next((r for r in checking['verification_refs'] if r['artifact_id'] == v['id']), None)
            _require(bound is not None, 'verification_binding_mismatch')
            inputs.reference(bound, 'verifications', 'Verification')
            required_outcome = 'supported' if target == 'resolved' else 'refuted'
            reason = 'resolution_evidence_missing' if target == 'resolved' else 'new_conflict_required'
            _require(result['outcome'] == required_outcome and bool(result['output_refs'])
                     and issue['resolution_condition'] in result['checked_scope'], reason)
            if target == 'resolved':
                verifier = inputs.assignment(v['owner_assignment_id'])
                _require(actor['actor_id'] not in {verifier['actor_id'], v['producer_id'], result['producer_id']},
                         'independent_resolver_required')
            for evidence in [*result['output_refs'], *result['observation_refs']]:
                inputs.reference(evidence)
            # The result must first occur after checking / the latest resolution.
            boundary = checking if target == 'resolved' else prior[-1]
            for _, historical in inputs.history:
                historical_events = historical['state'].get('issue_events', [])
                if boundary in historical_events:
                    if target == 'reopened':
                        old_content = {_evidence_content(inputs.objects[digest])
                                       for digest in historical['objects']}
                        _require(any(_evidence_content(inputs.objects[ref['sha256']]) not in old_content
                                     for ref in result['output_refs']), 'new_conflict_required')
                    break
                _require(result['id'] not in historical['state'].get('verification_results', {}), reason)
    elif target == 'transferred':
        owner = inputs.assignment(event['owner_assignment_id'])
        _require(owner['role'] == 'owner' and owner['milestone'] == event['to_milestone'], 'transfer_owner_mismatch')
        v = inputs.verification(event['verification_id'], issue['id'])
        _require(v['owner_assignment_id'] == owner['id'], 'verification_owner_mismatch')
        acceptance = inputs.registered('transfer_acceptances', event['acceptance_event_id'])
        expected = dict(id=event['acceptance_event_id'], project_id=project, issue_id=issue['id'],
            owner_assignment_id=owner['id'], verification_id=v['id'], to_milestone=event['to_milestone'],
            accepted=True, producer_id=owner['actor_id'])
        _require(acceptance == expected and acceptance['accepted'] is True, 'transfer_acceptance_invalid')
        accepted_state = next(h['state'] for _, h in inputs.history
                              if h['state'].get('transfer_acceptances', {}).get(acceptance['id']) == acceptance)
        _require(accepted_state.get('verifications', {}).get(v['id']) == v
                 and accepted_state.get('assignments', {}).get(owner['id']) == owner,
                 'transfer_acceptance_stale')
    elif target == 'superseded':
        _require(len(set(event['successor_ids'])) == len(event['successor_ids']) and all(
            identity != issue['id'] and identity in issues and issues[identity]['project_id'] == project
            and state.get('issue_states', {}).get(identity, 'open') not in ('resolved', 'superseded')
            for identity in event['successor_ids']), 'issue_successor_invalid')
    if target not in ('checking', 'resolved', 'reopened'):
        for ref in event['verification_refs']:
            inputs.reference(ref)
    patch = {'issue_events': [*events, event],
             'issue_states': {**state.get('issue_states', {}), issue['id']: target}}
    objects = {f"issue-events/{event['id']}": store._canonical(event)}
    if new_issue:
        patch['issues'] = {**issues, issue['id']: issue}
        objects[f"issues/{issue['id']}"] = store._canonical(issue)
    return {'state_patch': patch, 'event': {**store._VERSION, 'type': 'issue_event', 'payload': event}, 'object_inputs': objects}
