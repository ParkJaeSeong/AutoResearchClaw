"""Synthetic policy fixtures; no real research or runtime prerequisite seeding."""
from copy import deepcopy
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import commands, store


def uid():
    return str(uuid4())


def envelope(project, producer='owner'):
    return {**store._VERSION, 'project_id': project, 'id': uid(), 'event_id': uid(),
            'producer_id': producer, 'content_origin': 'synthetic',
            'provenance_status': 'declared_only', 'observation_refs': []}


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(root, topic='A04 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.owner = self.assignment('owner', 'owner', 'M1')
        self.resolver = self.assignment('resolver', 'resolver', 'M1')
        self.destination = self.assignment('destination', 'owner', 'M2')
        self.issue = {**envelope(self.project), 'origin': {'milestone': 'M1', 'node': 'review', 'attempt': uid(), 'local_issue_id': 'q1'},
            'question': 'Does the source support the claim?', 'category': 'source', 'target_refs': [],
            'severity': 'blocking', 'blocking_scope': [{'kind': 'handoff', 'milestone': 'M1', 'target_id': 'M2'}],
            'resolution_condition': 'Independent source comparison supports the claim', 'owner_assignment_id': self.owner['id']}
        self.register('assignments', self.owner, self.resolver, self.destination)

    def assignment(self, actor, role, milestone):
        return dict(id=uid(), project_id=self.project, actor_id=actor, role=role, milestone=milestone, active=True)

    def register(self, collection, *records):
        state = deepcopy(self.head['state'])
        state.setdefault(collection, {}).update({r['id']: r for r in records})
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}},
            objects={r['id']: store._canonical(r) for r in records})
        return [dict(project_id=self.project, head_id=self.head['id'], artifact_id=r['id'], sha256=store._hash(store._canonical(r))) for r in records]

    def event(self, before, after, actor=None, **extra):
        actor = actor or self.owner
        return {**envelope(self.project, actor['actor_id']), 'issue_id': self.issue['id'], 'from_status': before,
                'to_status': after, 'actor_assignment_id': actor['id'], 'rationale': 'Synthetic policy check',
                'verification_refs': [], 'successor_ids': [], **extra}

    def apply(self, event, issue=None):
        self.head = commands.apply_command(self.root, operation='issue.event', payload={'issue': issue, 'event': event},
                                          expected_head=self.head['id'], command_id=uid())
        return self.head

    def open(self):
        return self.apply(self.event(None, 'open'), self.issue)

    def verification(self, owner=None):
        owner = owner or self.owner
        budget = {**envelope(self.project), 'budget': 'fixture only'}
        budget_ref = self.register('fixture_budgets', budget)[0]
        verification = {**envelope(self.project, owner['actor_id']), 'issue_ids': [self.issue['id']], 'method': 'source_check',
            'question': self.issue['question'], 'input_refs': [], 'acceptance_rule': self.issue['resolution_condition'],
            'owner_assignment_id': owner['id'], 'budget_ref': budget_ref}
        return verification, self.register('verifications', verification)[0]

    def result(self, verification, outcome='supported'):
        output = {**envelope(self.project), 'observation': f'synthetic source comparison: {outcome}'}
        output_ref = self.register('fixture_outputs', output)[0]
        result = {**envelope(self.project), 'verification_id': verification['id'], 'output_refs': [output_ref],
                  'outcome': outcome, 'checked_scope': [self.issue['resolution_condition']], 'limitations': ['synthetic']}
        return result, self.register('verification_results', result)[0]

    def checking(self):
        self.open()
        verification, ref = self.verification()
        self.apply(self.event('open', 'checking', verification_refs=[ref]))
        return verification


def reject(f, event, reason, issue=None):
    before = store.read_head(f.root)
    with pytest.raises(ValueError, match=f'^{reason}$'):
        f.apply(event, issue)
    assert store.read_head(f.root) == before


def test_append_only_creation_and_exact_from_status(tmp_path):
    f = Fixture(tmp_path / 'p')
    f.open()
    old = deepcopy(f.head)
    reject(f, f.event('checking', 'deferred'), 'issue_from_status_mismatch')
    f.apply(f.event('open', 'deferred'))
    assert f.head['state']['issues'][f.issue['id']] == f.issue
    assert f.head['state']['issue_events'][:1] == old['state']['issue_events']
    assert len(f.head['state']['issue_events']) == 2
    assert f.head['state']['issue_states'][f.issue['id']] == 'deferred'


def test_transferred_is_unresolved_and_resolution_evidence_missing(tmp_path):
    f = Fixture(tmp_path / 'p'); f.open()
    verification, ref = f.verification(f.destination)
    acceptance = dict(id=uid(), project_id=f.project, issue_id=f.issue['id'], owner_assignment_id=f.destination['id'],
        verification_id=verification['id'], to_milestone='M2', accepted=True, producer_id='destination')
    f.register('transfer_acceptances', acceptance)
    f.apply(f.event('open', 'transferred', to_milestone='M2', owner_assignment_id=f.destination['id'],
        verification_id=verification['id'], acceptance_event_id=acceptance['id']))
    assert f.head['state']['issue_states'][f.issue['id']] == 'transferred'
    reject(f, f.event('transferred', 'resolved', f.resolver), 'resolution_evidence_missing')
    f.apply(f.event('transferred', 'checking', f.destination, verification_refs=[ref]))
    _, result_ref = f.result(verification)
    f.apply(f.event('checking', 'resolved', f.resolver, verification_refs=[result_ref]))
    assert f.head['state']['issue_states'][f.issue['id']] == 'resolved'


def test_resolution_and_new_conflict_reopen_preserve_referenced_bytes(tmp_path):
    f = Fixture(tmp_path / 'p'); verification = f.checking()
    _, ref = f.result(verification)
    path = store._store_path(f.root) / 'objects' / ref['sha256']; original = path.read_bytes()
    f.apply(f.event('checking', 'resolved', f.resolver, verification_refs=[ref]))
    reject(f, f.event('resolved', 'reopened', verification_refs=[ref]), 'new_conflict_required')
    _, conflict = f.result(verification, 'refuted')
    f.apply(f.event('resolved', 'reopened', verification_refs=[conflict]))
    assert f.head['state']['issue_states'][f.issue['id']] == 'reopened'
    assert path.read_bytes() == original


@pytest.mark.parametrize('fault,reason', [('foreign', 'issue_reference_invalid'), ('invented', 'issue_reference_invalid'),
    ('hash', 'issue_reference_invalid'), ('wrong_issue', 'verification_issue_mismatch'),
    ('self', 'independent_resolver_required'), ('inconclusive', 'resolution_evidence_missing'),
    ('unregistered', 'issue_reference_invalid'), ('stale', 'issue_reference_stale')])
def test_resolution_rejects_bad_evidence_and_preserves_head(tmp_path, fault, reason):
    f = Fixture(tmp_path / 'p'); verification = f.checking()
    if fault == 'wrong_issue':
        verification = {**verification, 'issue_ids': [uid()]}; f.register('verifications', verification)
    result, ref = f.result(verification, 'inconclusive' if fault == 'inconclusive' else 'supported')
    actor = f.resolver
    if fault == 'foreign': ref['project_id'] = uid()
    if fault == 'invented': ref['head_id'] = 'a' * 64
    if fault == 'hash': ref['sha256'] = 'b' * 64
    if fault == 'self': actor = f.owner
    if fault == 'unregistered': ref['artifact_id'] = uid()
    if fault == 'stale': f.register('verification_results', {**result, 'limitations': ['new revision']})
    reject(f, f.event('checking', 'resolved', actor, verification_refs=[ref]), reason)


def test_imported_pending_cannot_resolve_or_replace_issue(tmp_path):
    f = Fixture(tmp_path / 'p')
    f.issue['owner_assignment_id'] = None
    state = deepcopy(f.head['state']); state.update(issues={f.issue['id']: f.issue}, issue_events=[],
        imported_issue_states={f.issue['id']: {'source_status': 'resolved', 'import_state': 'pending_policy_revalidation'}})
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_import', 'payload': {}}, objects={})
    reject(f, f.event('open', 'resolved', f.resolver), 'resolution_evidence_missing')
    reject(f, f.event(None, 'open'), 'issue_already_exists', f.issue)
    verification, ref = f.verification()
    reject(f, f.event('open', 'checking', verification_refs=[ref]), 'issue_owner_required')
    f.apply(f.event('open', 'checking', owner_assignment_id=f.owner['id'], verification_refs=[ref]))
    _, result = f.result(verification)
    f.apply(f.event('checking', 'resolved', f.resolver, verification_refs=[result]))
    assert f.head['state']['imported_issue_states'][f.issue['id']]['import_state'] == 'pending_policy_revalidation'
    assert f.head['state']['imported_issue_states'][f.issue['id']]['source_status'] == 'resolved'
    assert f.head['state']['issues'][f.issue['id']]['owner_assignment_id'] is None


def test_payload_cannot_supply_trusted_context(tmp_path):
    f = Fixture(tmp_path / 'p')
    with pytest.raises(ValueError, match='issue_payload_invalid'):
        commands.apply_command(f.root, operation='issue.event', payload={'issue': f.issue, 'event': f.event(None, 'open'), '_issue_context': {}},
                               expected_head=f.head['id'], command_id=uid())


@pytest.mark.parametrize('fault,reason', [('absent', 'issue_prerequisite_missing'), ('unbacked', 'issue_prerequisite_unbacked'),
    ('producer', 'transfer_acceptance_invalid'), ('issue', 'transfer_acceptance_invalid'),
    ('verification', 'transfer_acceptance_invalid'), ('destination', 'transfer_owner_mismatch')])
def test_transfer_requires_real_destination_acceptance(tmp_path, fault, reason):
    f = Fixture(tmp_path / 'p'); f.open()
    verification, _ = f.verification(f.destination)
    acceptance = dict(id=uid(), project_id=f.project, issue_id=f.issue['id'], owner_assignment_id=f.destination['id'],
        verification_id=verification['id'], to_milestone='M2', accepted=True, producer_id='destination')
    if fault == 'producer': acceptance['producer_id'] = 'owner'
    if fault == 'issue': acceptance['issue_id'] = uid()
    if fault == 'verification': acceptance['verification_id'] = uid()
    if fault not in ('absent', 'unbacked'): f.register('transfer_acceptances', acceptance)
    if fault == 'unbacked':
        state = deepcopy(f.head['state']); state['transfer_acceptances'] = {acceptance['id']: acceptance}
        f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_unbacked', 'payload': {}}, objects={})
    reject(f, f.event('open', 'transferred', to_milestone='M3' if fault == 'destination' else 'M2',
        owner_assignment_id=f.destination['id'], verification_id=verification['id'], acceptance_event_id=acceptance['id']), reason)


def test_supersession_requires_existing_open_successor_and_preserves_original(tmp_path):
    f = Fixture(tmp_path / 'p'); f.open()
    original = deepcopy(f.issue)
    reject(f, f.event('open', 'superseded', successor_ids=[uid()]), 'issue_successor_invalid')
    reject(f, f.event('open', 'superseded', successor_ids=[f.issue['id']]), 'issue_successor_invalid')
    successor = {**f.issue, 'id': uid(), 'event_id': uid(), 'question': 'Narrower question'}
    event = f.event(None, 'open'); event['issue_id'] = successor['id']
    f.apply(event, successor)
    f.apply(f.event('open', 'superseded', successor_ids=[successor['id']]))
    assert f.head['state']['issues'][original['id']] == original
    assert f.head['state']['issue_states'][original['id']] == 'superseded'
    assert f.head['state']['issue_events'][-1]['successor_ids'] == [successor['id']]


def test_pure_plan_has_no_io_and_cannot_use_bare_snapshot(tmp_path, monkeypatch):
    from researchclaw.core.research_graph.issues import propose_issue_event
    f = Fixture(tmp_path / 'p')
    payload = {'issue': f.issue, 'event': f.event(None, 'open')}
    with pytest.raises(ValueError, match='issue_context_missing'):
        propose_issue_event(f.head, payload)
    snapshot = deepcopy(f.head)
    base = store._store_path(f.root)
    snapshot['_issue_context'] = {'history': store._history(base),
        'objects': {digest: (base / 'objects' / digest).read_bytes() for digest in f.head['objects']}}
    before, before_payload = deepcopy(snapshot), deepcopy(payload)
    def forbidden(*args, **kwargs):
        raise AssertionError('pure policy performed I/O')
    monkeypatch.setattr(store, '_read_file', forbidden)
    monkeypatch.setattr(store, '_history', forbidden)
    plan = propose_issue_event(snapshot, payload)
    assert snapshot == before and payload == before_payload
    assert set(plan) == {'state_patch', 'event', 'object_inputs'}
    assert len(plan['object_inputs']) == 2


def test_result_on_unrelated_ancestor_and_prior_conflict_rejected(tmp_path):
    f = Fixture(tmp_path / 'p'); verification = f.checking()
    before_result = f.head['id']
    _, conflict = f.result(verification, 'refuted')
    _, result = f.result(verification)
    wrong_ancestor = {**result, 'head_id': before_result}
    reject(f, f.event('checking', 'resolved', f.resolver, verification_refs=[wrong_ancestor]), 'issue_reference_invalid')
    f.apply(f.event('checking', 'resolved', f.resolver, verification_refs=[result]))
    reject(f, f.event('resolved', 'reopened', verification_refs=[conflict]), 'new_conflict_required')


def test_replay_and_stale_head_are_atomic(tmp_path):
    f = Fixture(tmp_path / 'p')
    old_head = f.head['id']; command_id = uid()
    payload = {'issue': f.issue, 'event': f.event(None, 'open')}
    first = commands.apply_command(f.root, operation='issue.event', payload=payload, expected_head=old_head, command_id=command_id)
    replay = commands.apply_command(f.root, operation='issue.event', payload=payload, expected_head=old_head, command_id=command_id)
    assert replay == first
    with pytest.raises(ValueError, match='research_graph_head_conflict'):
        commands.apply_command(f.root, operation='issue.event', payload=payload, expected_head=old_head, command_id=uid())
    assert store.read_head(f.root) == first


def test_checking_rejects_acceptance_rule_not_bound_to_issue(tmp_path):
    f = Fixture(tmp_path / 'p'); f.open()
    verification, _ = f.verification()
    verification['acceptance_rule'] = 'Some unrelated acceptance rule'
    ref = f.register('verifications', verification)[0]
    reject(f, f.event('open', 'checking', verification_refs=[ref]), 'verification_binding_mismatch')


def test_transfer_rejects_verification_changed_after_acceptance(tmp_path):
    f = Fixture(tmp_path / 'p'); f.open()
    verification, _ = f.verification(f.destination)
    acceptance = dict(id=uid(), project_id=f.project, issue_id=f.issue['id'], owner_assignment_id=f.destination['id'],
        verification_id=verification['id'], to_milestone='M2', accepted=True, producer_id='destination')
    f.register('transfer_acceptances', acceptance)
    f.register('verifications', {**verification, 'question': 'Changed after acceptance'})
    reject(f, f.event('open', 'transferred', to_milestone='M2', owner_assignment_id=f.destination['id'],
        verification_id=verification['id'], acceptance_event_id=acceptance['id']), 'transfer_acceptance_stale')


@pytest.mark.parametrize('clone_output', [False, True])
def test_reopen_rejects_old_conflict_cloned_with_new_id_and_preserves_head(tmp_path, clone_output):
    f = Fixture(tmp_path / 'p'); verification = f.checking()
    old_conflict, _ = f.result(verification, 'refuted')
    _, supported = f.result(verification)
    f.apply(f.event('checking', 'resolved', f.resolver, verification_refs=[supported]))
    clone = {**old_conflict, 'id': uid(), 'event_id': uid()}
    if clone_output:
        old_output = f.head['state']['fixture_outputs'][old_conflict['output_refs'][0]['artifact_id']]
        clone['output_refs'] = f.register('fixture_outputs', {**old_output, 'id': uid(), 'event_id': uid()})
    ref = f.register('verification_results', clone)[0]
    reject(f, f.event('resolved', 'reopened', verification_refs=[ref]), 'new_conflict_required')
