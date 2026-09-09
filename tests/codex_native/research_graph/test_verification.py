"""Synthetic A05 fixtures; registration is not experiment execution."""
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
    def __init__(self, root, *, register_issue=True):
        self.root = root
        self.head = commands.init_project(root, topic='A05 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.owner = dict(id=uid(), project_id=self.project, actor_id='owner', role='owner',
                          milestone='M1', active=True)
        self.resolver = dict(id=uid(), project_id=self.project, actor_id='resolver', role='resolver',
                             milestone='M1', active=True)
        self.issue = {**envelope(self.project),
            'origin': {'milestone': 'M1', 'node': 'review', 'attempt': uid(), 'local_issue_id': 'q1'},
            'question': 'Does the source support the claim?', 'category': 'source',
            'target_refs': [], 'severity': 'blocking',
            'blocking_scope': [{'kind': 'finalization', 'milestone': 'M1', 'target_id': 'report'}],
            'resolution_condition': 'Independent source comparison supports the claim',
            'owner_assignment_id': self.owner['id']}
        budget = {**envelope(self.project), 'budget': 'fixture only'}
        source = {**envelope(self.project), 'text': 'source fixture'}
        self.register('assignments', self.owner, self.resolver)
        if register_issue:
            self.register('issues', self.issue)
        self.budget_ref = self.register('fixture_budgets', budget)[0]
        self.input_ref = self.register('fixture_inputs', source)[0]

    def register(self, collection, *records):
        state = deepcopy(self.head['state'])
        state.setdefault(collection, {}).update({record['id']: record for record in records})
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}},
            objects={record['id']: store._canonical(record) for record in records})
        return [dict(project_id=self.project, head_id=self.head['id'], artifact_id=record['id'],
                     sha256=store._hash(store._canonical(record))) for record in records]

    def verification(self, **changes):
        record = {**envelope(self.project), 'issue_ids': [self.issue['id']], 'method': 'source_check',
            'question': self.issue['question'], 'input_refs': [self.input_ref],
            'acceptance_rule': self.issue['resolution_condition'],
            'owner_assignment_id': self.owner['id'], 'budget_ref': self.budget_ref}
        record.update(changes)
        return record

    def apply(self, operation, payload):
        self.head = commands.apply_command(self.root, operation=operation, payload=payload,
            expected_head=self.head['id'], command_id=uid())
        return self.head

    def prepare(self, record=None):
        record = record or self.verification()
        return record, self.apply('verification.prepare', {'verification': record})

    def result(self, verification, verification_head, outcome='supported', **changes):
        output = {**envelope(self.project), 'observation': f'synthetic check: {outcome}'}
        output_ref = self.register('fixture_outputs', output)[0]
        verification_ref = dict(project_id=self.project, head_id=verification_head,
            artifact_id=verification['id'], sha256=store._hash(store._canonical(verification)))
        result = {**envelope(self.project), 'verification_id': verification['id'],
            'output_refs': [output_ref], 'outcome': outcome,
            'checked_scope': [verification['acceptance_rule']], 'limitations': ['synthetic fixture']}
        result.update(changes)
        return result, verification_ref

    def empty_output_ref(self):
        name = f'fixture-empty-outputs/{uid()}'
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(),
            state=deepcopy(self.head['state']),
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}},
            objects={name: b''})
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=name,
                    sha256=store._hash(b''))

    def issue_event(self, before, after, actor=None, **changes):
        actor = actor or self.owner
        event = {**envelope(self.project, actor['actor_id']), 'issue_id': self.issue['id'],
            'from_status': before, 'to_status': after, 'actor_assignment_id': actor['id'],
            'rationale': 'Synthetic policy transition', 'verification_refs': [], 'successor_ids': []}
        event.update(changes)
        return event


def reject(fixture, operation, payload, reason):
    before = store.read_head(fixture.root)
    with pytest.raises(ValueError, match=f'^{reason}$'):
        fixture.apply(operation, payload)
    assert store.read_head(fixture.root) == before


def test_prepare_and_result_bind_exact_revision_and_preserve_referenced_bytes(tmp_path):
    f = Fixture(tmp_path / 'p')
    verification = f.verification()
    referenced_path = store._store_path(f.root) / 'objects' / f.input_ref['sha256']
    referenced_before = referenced_path.read_bytes()
    _, prepared = f.prepare(verification)
    result, verification_ref = f.result(verification, prepared['id'])
    registered = f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})

    assert registered['state']['verifications'][verification['id']] == verification
    assert registered['state']['verification_results'][result['id']] == result
    assert registered['state'].get('issue_states', {}) == {}
    assert registered['events'][-1]['type'] == 'verification_result_registered'
    assert referenced_path.read_bytes() == referenced_before


def test_prepare_rejects_acceptance_rule_missing_and_preserves_head(tmp_path):
    f = Fixture(tmp_path / 'p')
    reject(f, 'verification.prepare', {'verification': f.verification(acceptance_rule='')},
           'acceptance_rule_missing')


@pytest.mark.parametrize('outcome', ['failed', 'inconclusive'])
def test_non_success_result_remains_distinct_and_does_not_resolve_issue(tmp_path, outcome):
    f = Fixture(tmp_path / 'p')
    verification, prepared = f.prepare()
    result, verification_ref = f.result(verification, prepared['id'], outcome,
        output_refs=[], checked_scope=[], limitations=[f'{outcome} before acceptance evaluation'])
    registered = f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})

    assert registered['state']['verification_results'][result['id']]['outcome'] == outcome
    assert registered['state'].get('issue_states', {}) == {}
    assert registered['state'].get('issue_events', []) == []


@pytest.mark.parametrize('fault,reason', [
    ('foreign', 'issue_reference_invalid'),
    ('fake_head', 'issue_reference_invalid'),
    ('fake_hash', 'issue_reference_invalid'),
    ('replacement', 'verification_exists'),
    ('stale_input', 'issue_reference_stale'),
])
def test_prepare_rejects_invalid_or_replacement_bindings_and_preserves_head(tmp_path, fault, reason):
    f = Fixture(tmp_path / 'p')
    verification = f.verification()
    if fault == 'foreign':
        verification['input_refs'][0]['project_id'] = uid()
    elif fault == 'fake_head':
        verification['input_refs'][0]['head_id'] = 'a' * 64
    elif fault == 'fake_hash':
        verification['input_refs'][0]['sha256'] = 'b' * 64
    elif fault == 'replacement':
        f.prepare(verification)
        verification = {**verification, 'question': 'Replacement under the same id'}
    else:
        changed = {**f.head['state']['fixture_inputs'][f.input_ref['artifact_id']], 'text': 'changed'}
        f.register('fixture_inputs', changed)
    reject(f, 'verification.prepare', {'verification': verification}, reason)


@pytest.mark.parametrize('fault,reason', [
    ('foreign', 'issue_reference_invalid'),
    ('fake_head', 'issue_reference_invalid'),
    ('fake_hash', 'issue_reference_invalid'),
    ('wrong_id', 'verification_binding_mismatch'),
    ('stale_revision', 'issue_reference_stale'),
    ('stale_dependency', 'issue_reference_stale'),
    ('owner_role', 'verification_owner_mismatch'),
    ('replacement', 'verification_result_exists'),
])
def test_result_rejects_invalid_or_replacement_verification_binding_and_preserves_head(tmp_path, fault, reason):
    f = Fixture(tmp_path / 'p')
    verification, prepared = f.prepare()
    result, verification_ref = f.result(verification, prepared['id'])
    if fault == 'foreign':
        verification_ref['project_id'] = uid()
    elif fault == 'fake_head':
        verification_ref['head_id'] = 'a' * 64
    elif fault == 'fake_hash':
        verification_ref['sha256'] = 'b' * 64
    elif fault == 'wrong_id':
        result['verification_id'] = uid()
    elif fault == 'stale_revision':
        changed = {**verification, 'question': 'Changed criteria'}
        f.register('verifications', changed)
    elif fault == 'stale_dependency':
        changed = {**f.head['state']['fixture_inputs'][f.input_ref['artifact_id']], 'text': 'changed'}
        f.register('fixture_inputs', changed)
    elif fault == 'owner_role':
        f.register('assignments', {**f.owner, 'role': 'resolver'})
    elif fault == 'replacement':
        f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})
        result = {**result, 'limitations': ['replacement under the same id']}
    reject(f, 'verification.result', {'verification_ref': verification_ref, 'result': result}, reason)


@pytest.mark.parametrize('fault,reason', [
    ('no_output', 'verification_output_missing'),
    ('scope', 'verification_scope_missing'),
    ('failure_without_limitation', 'verification_limitation_missing'),
])
def test_result_rejects_unsupported_outcome_evidence_shape(tmp_path, fault, reason):
    f = Fixture(tmp_path / 'p')
    verification, prepared = f.prepare()
    result, verification_ref = f.result(verification, prepared['id'])
    if fault == 'no_output':
        result['output_refs'] = []
    elif fault == 'scope':
        result['checked_scope'] = ['Unrelated scope']
    else:
        result.update(outcome='failed', output_refs=[], checked_scope=[], limitations=[])
    reject(f, 'verification.result', {'verification_ref': verification_ref, 'result': result}, reason)


def test_supported_result_can_feed_native_independent_resolution(tmp_path):
    f = Fixture(tmp_path / 'p', register_issue=False)
    f.apply('issue.event', {'issue': f.issue, 'event': f.issue_event(None, 'open')})
    verification, prepared = f.prepare()
    verification_ref = dict(project_id=f.project, head_id=prepared['id'], artifact_id=verification['id'],
        sha256=store._hash(store._canonical(verification)))
    f.apply('issue.event', {'issue': None,
        'event': f.issue_event('open', 'checking', verification_refs=[verification_ref])})
    result, _ = f.result(verification, prepared['id'])
    registered = f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})
    result_ref = dict(project_id=f.project, head_id=registered['id'], artifact_id=result['id'],
        sha256=store._hash(store._canonical(result)))
    resolved = f.apply('issue.event', {'issue': None,
        'event': f.issue_event('checking', 'resolved', f.resolver, verification_refs=[result_ref])})

    assert resolved['state']['issue_states'][f.issue['id']] == 'resolved'
    assert resolved['state']['verifications'][verification['id']] == verification
    assert resolved['state']['verification_results'][result['id']] == result


@pytest.mark.parametrize('outcome', ['failed', 'inconclusive'])
def test_non_success_native_result_stays_checking_when_resolution_is_attempted(tmp_path, outcome):
    f = Fixture(tmp_path / 'p', register_issue=False)
    f.apply('issue.event', {'issue': f.issue, 'event': f.issue_event(None, 'open')})
    verification, prepared = f.prepare()
    verification_ref = dict(project_id=f.project, head_id=prepared['id'], artifact_id=verification['id'],
        sha256=store._hash(store._canonical(verification)))
    f.apply('issue.event', {'issue': None,
        'event': f.issue_event('open', 'checking', verification_refs=[verification_ref])})
    result, _ = f.result(verification, prepared['id'], outcome,
        output_refs=[], checked_scope=[], limitations=[f'{outcome} before acceptance evaluation'])
    registered = f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})
    result_ref = dict(project_id=f.project, head_id=registered['id'], artifact_id=result['id'],
        sha256=store._hash(store._canonical(result)))

    reject(f, 'issue.event', {'issue': None,
        'event': f.issue_event('checking', 'resolved', f.resolver, verification_refs=[result_ref])},
        'resolution_evidence_missing')
    assert f.head['state']['issue_states'][f.issue['id']] == 'checking'


@pytest.mark.parametrize('outcome', ['supported', 'refuted'])
def test_evidentiary_result_rejects_empty_output_bytes_and_native_issue_stays_checking(tmp_path, outcome):
    f = Fixture(tmp_path / 'p', register_issue=False)
    f.apply('issue.event', {'issue': f.issue, 'event': f.issue_event(None, 'open')})
    verification, prepared = f.prepare()
    verification_ref = dict(project_id=f.project, head_id=prepared['id'], artifact_id=verification['id'],
        sha256=store._hash(store._canonical(verification)))
    f.apply('issue.event', {'issue': None,
        'event': f.issue_event('open', 'checking', verification_refs=[verification_ref])})
    empty_ref = f.empty_output_ref()
    result = {**envelope(f.project), 'verification_id': verification['id'],
        'output_refs': [empty_ref], 'outcome': outcome,
        'checked_scope': [verification['acceptance_rule']], 'limitations': ['synthetic fixture']}

    reject(f, 'verification.result', {'verification_ref': verification_ref, 'result': result},
           'verification_output_missing')
    assert f.head['state']['issue_states'][f.issue['id']] == 'checking'


def test_prepare_replay_and_stale_head_are_atomic(tmp_path):
    f = Fixture(tmp_path / 'p')
    verification = f.verification()
    payload = {'verification': verification}
    old_head, command_id = f.head['id'], uid()
    args = dict(operation='verification.prepare', payload=payload,
                expected_head=old_head, command_id=command_id)
    first = commands.apply_command(f.root, **args)
    assert commands.apply_command(f.root, **args) == first
    with pytest.raises(ValueError, match='^research_graph_head_conflict$'):
        commands.apply_command(f.root, operation='verification.prepare',
            payload={'verification': {**verification, 'id': uid(), 'event_id': uid()}},
            expected_head=old_head, command_id=uid())
    assert store.read_head(f.root) == first


def test_pure_prepare_requires_trusted_context_and_does_no_io(tmp_path, monkeypatch):
    from researchclaw.core.research_graph.verification import prepare_verification

    f = Fixture(tmp_path / 'p')
    payload = {'verification': f.verification()}
    with pytest.raises(ValueError, match='^issue_context_missing$'):
        prepare_verification(f.head, payload)
    snapshot = deepcopy(f.head)
    base = store._store_path(f.root)
    snapshot['_issue_context'] = {'history': store._history(base),
        'objects': {digest: (base / 'objects' / digest).read_bytes() for digest in f.head['objects']}}
    before_snapshot, before_payload = deepcopy(snapshot), deepcopy(payload)

    def forbidden(*args, **kwargs):
        raise AssertionError('pure verification policy performed I/O')

    monkeypatch.setattr(store, '_read_file', forbidden)
    monkeypatch.setattr(store, '_history', forbidden)
    plan = prepare_verification(snapshot, payload)
    assert snapshot == before_snapshot and payload == before_payload
    assert set(plan) == {'state_patch', 'event', 'object_inputs'}


def test_payload_cannot_supply_private_context(tmp_path):
    f = Fixture(tmp_path / 'p')
    reject(f, 'verification.prepare',
        {'verification': f.verification(), '_issue_context': {}}, 'verification_payload_invalid')
