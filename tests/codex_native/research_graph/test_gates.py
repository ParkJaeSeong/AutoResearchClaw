"""Synthetic A07 policy fixtures; no scientific validation or prerequisite producer."""
from copy import deepcopy
from uuid import uuid4
import importlib
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.contracts import validate_record


def uid():
    return str(uuid4())


def assess(snapshot, milestone='M1', gate_id=None):
    module = importlib.import_module('researchclaw.core.research_graph.gates')
    return module.assess_gate(snapshot, milestone=milestone, gate_id=gate_id)


class Fixture:
    def __init__(self, root, milestone='M1', category='empirical', severity='blocking'):
        self.root, self.milestone = root, milestone
        self.head = commands.init_project(root, topic='A07 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.author = self.assignment('author', 'owner', milestone)
        roles = ('domain', 'methodology', 'critical') if milestone == 'M1' else ('domain', 'methodology', 'reproducibility')
        self.reviewers = {r: self.assignment(r, 'resolver', milestone) for r in roles}
        self.destination = self.assignment('destination', 'owner', 'M2' if milestone == 'M1' else 'M3')
        self.register('assignments', self.author, *self.reviewers.values(), self.destination)
        self.binding = self.register('fixture_inputs', {**self.envelope(), 'text': 'frozen packet'})[0]
        self.source = self.register('fixture_sources', {**self.envelope(), 'text': 'original source'})[0]
        self.issue = {**self.envelope(), 'origin': {'milestone': milestone, 'node': 'review', 'attempt': uid(), 'local_issue_id': 'q'},
            'question': 'Does the experiment reproduce the effect?', 'category': category, 'target_refs': [self.source],
            'severity': severity, 'blocking_scope': [{'kind': 'handoff', 'milestone': milestone, 'target_id': self.destination['milestone']}],
            'resolution_condition': 'Fixed criterion is met', 'owner_assignment_id': self.author['id']}
        self.apply(self.event(None, 'open'), self.issue)
        session = {'id': uid(), 'project_id': self.project, 'input_binding': self.binding,
            'participant_assignment_ids': [a['id'] for a in self.reviewers.values()], 'frozen': True}
        self.register('review_sessions', session)
        self.positions = [{**self.envelope(a['actor_id']), 'assignment_id': a['id'], 'session_id': session['id'],
            'input_binding': self.binding, 'issue_id': self.issue['id'], 'stance': 'conditional', 'rationale': 'Await experiment',
            'evidence_refs': [self.source], 'changed_from': None, 'change_kind': None} for a in self.reviewers.values()]
        self.position_refs = self.register('positions', *self.positions)
        result = {**self.envelope(), 'verification_id': uid(), 'output_refs': [self.source], 'outcome': 'inconclusive',
            'checked_scope': ['synthetic source comparison'], 'limitations': ['Empirical question remains']}
        result_ref = self.register('verification_results', result)[0]
        acknowledgements = [{'id': uid(), 'project_id': self.project, 'assignment_id': p['assignment_id'],
            'producer_id': p['producer_id'], 'position_ref': ref, 'claim_ref': self.binding,
            'summary': 'Empirical uncertainty remains', 'disposition': 'inconclusive', 'acknowledged': True}
            for p, ref in zip(self.positions, self.position_refs)]
        ack_refs = self.register('position_acknowledgements', *acknowledgements)
        self.decision = {**self.envelope('coordinator'), 'issue_ids': [self.issue['id']], 'position_refs': self.position_refs,
            'claim_dispositions': [{'claim_ref': self.binding, 'disposition': 'inconclusive', 'rationale': 'Empirical uncertainty remains'}],
            'rationale_links': [{'claim_ref': self.binding, 'position_refs': self.position_refs, 'verification_refs': [result_ref], 'acknowledgement_refs': ack_refs}],
            'dissent': [], 'next_action': {'kind': 'handoff', 'milestone': milestone, 'node': 'review', 'attempt': uid(), 'rationale': 'Transfer fixed question'},
            'gate_result': {'ready': True, 'reason_codes': [], 'required_actions': [], 'unresolved_issue_ids': []}}
        decision_ref = self.register('decisions', self.decision)[0]
        receipt = self.register('approval_receipts', {'id': uid(), 'project_id': self.project, 'producer_id': 'existing-user-authority',
            'decision': 'approved', 'binding': self.binding, 'scope_refs': [self.binding]})[0]
        self.approval = {**self.envelope('existing-approval-adapter'), 'existing_receipt_ref': receipt,
            'scope_refs': [self.binding], 'binding': self.binding, 'validity': 'valid'}
        approval_ref = self.register('approval_bindings', self.approval)[0]
        self.gate = {'id': uid(), 'project_id': self.project, 'milestone': milestone, 'kind': 'handoff',
            'target_id': self.destination['milestone'], 'input_binding': self.binding,
            'author_assignment_ids': [self.author['id']], 'required_roles': {r: a['id'] for r, a in self.reviewers.items()},
            'submission_refs': self.position_refs, 'source_refs': [self.source], 'approval_refs': [approval_ref], 'decision_ref': decision_ref}
        self.register('gate_requirements', self.gate)
        for kind, records in [('Issue', [self.issue]), ('Position', self.positions), ('Decision', [self.decision]), ('ApprovalBinding', [self.approval])]:
            assert all(validate_record(kind, record) == () for record in records)

    def envelope(self, producer='author'):
        return {**store._VERSION, 'project_id': self.project, 'id': uid(), 'event_id': uid(),
            'producer_id': producer, 'content_origin': 'synthetic', 'provenance_status': 'declared_only', 'observation_refs': []}

    def assignment(self, actor, role, milestone):
        return dict(id=uid(), project_id=self.project, actor_id=actor, role=role, milestone=milestone, active=True)

    def register(self, collection, *records):
        state = deepcopy(self.head['state'])
        state.setdefault(collection, {}).update({r['id']: r for r in records})
        self.commit(state, {r['id']: store._canonical(r) for r in records})
        return [dict(project_id=self.project, head_id=self.head['id'], artifact_id=r['id'], sha256=store._hash(store._canonical(r))) for r in records]

    def commit(self, state, objects=None):
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}}, objects=objects or {})

    def event(self, before, after, **extra):
        return {**self.envelope(), 'issue_id': self.issue['id'], 'from_status': before, 'to_status': after,
            'actor_assignment_id': self.author['id'], 'rationale': 'Synthetic event', 'verification_refs': [], 'successor_ids': [], **extra}

    def apply(self, event, issue=None):
        self.head = commands.apply_command(self.root, operation='issue.event', payload={'issue': issue, 'event': event}, expected_head=self.head['id'], command_id=uid())

    def transfer(self):
        v = {**self.envelope('destination'), 'issue_ids': [self.issue['id']], 'method': 'experiment', 'question': self.issue['question'],
            'input_refs': [self.binding], 'acceptance_rule': self.issue['resolution_condition'], 'owner_assignment_id': self.destination['id'], 'budget_ref': self.source}
        self.register('verifications', v)
        acceptance = dict(id=uid(), project_id=self.project, issue_id=self.issue['id'], owner_assignment_id=self.destination['id'],
            verification_id=v['id'], to_milestone=self.destination['milestone'], accepted=True, producer_id='destination')
        self.register('transfer_acceptances', acceptance)
        self.apply(self.event('open', 'transferred', to_milestone=self.destination['milestone'], owner_assignment_id=self.destination['id'], verification_id=v['id'], acceptance_event_id=acceptance['id']))
        return acceptance

    def assess(self):
        return assess(commands.read_policy_snapshot(self.root), self.milestone, self.gate['id'])


def test_m1_accepted_empirical_transfer_passes_and_preserves_unresolved_and_bytes(tmp_path):
    f = Fixture(tmp_path); f.transfer()
    snapshot = commands.read_policy_snapshot(tmp_path)
    before = deepcopy(snapshot)
    path = store._store_path(tmp_path) / 'objects' / f.source['sha256']
    old_bytes = path.read_bytes()
    assert assess(snapshot, gate_id=f.gate['id']) == {'ready': True, 'reason_codes': [], 'required_actions': [], 'unresolved_issue_ids': [f.issue['id']]}
    assert snapshot == before and store.read_head(tmp_path)['id'] == f.head['id']
    assert path.read_bytes() == old_bytes


def test_m2_integrity_transfer_still_blocks_and_ignores_ready_boolean(tmp_path):
    f = Fixture(tmp_path, 'M2', 'integrity'); f.transfer()
    result = f.assess()
    assert result['ready'] is False
    assert result['reason_codes'] == ['blocking_issue_unresolved']
    assert result['unresolved_issue_ids'] == [f.issue['id']]
    assert store.read_head(tmp_path)['id'] == f.head['id']


@pytest.mark.parametrize('field,reason', [('submission_refs', 'required_submission_missing'), ('source_refs', 'source_missing'), ('approval_refs', 'approval_missing')])
def test_missing_required_prerequisites_fail_closed(tmp_path, field, reason):
    f = Fixture(tmp_path); f.transfer()
    f.gate[field] = []; f.register('gate_requirements', f.gate)
    result = f.assess()
    assert result['ready'] is False and reason in result['reason_codes']


def test_optional_issue_remains_listed_without_blocking(tmp_path):
    f = Fixture(tmp_path, severity='optional')
    assert f.assess() == {'ready': True, 'reason_codes': [], 'required_actions': [], 'unresolved_issue_ids': [f.issue['id']]}


@pytest.mark.parametrize('validity', ['revoked', 'expired', 'unknown', 'needs_revalidation'])
def test_noncurrent_approval_rejected(tmp_path, validity):
    f = Fixture(tmp_path); f.transfer()
    f.approval['validity'] = validity
    f.gate['approval_refs'] = f.register('approval_bindings', f.approval)
    f.register('gate_requirements', f.gate)
    assert 'approval_not_current' in f.assess()['reason_codes']


def test_spoofed_status_and_imported_resolved_do_not_erase_native_block(tmp_path):
    f = Fixture(tmp_path)
    state = deepcopy(f.head['state']); state['issue_states'][f.issue['id']] = 'resolved'
    state['imported_issue_states'] = {f.issue['id']: {'source_status': 'resolved', 'import_state': 'pending_policy_revalidation'}}
    state['issue_events'] = []
    f.commit(state)
    before = deepcopy(f.head['state']['imported_issue_states'])
    assert f.assess()['reason_codes'] == ['blocking_issue_unresolved']
    assert store.read_head(tmp_path)['state']['imported_issue_states'] == before


def test_required_role_cannot_be_author_and_missing_role_fails_closed(tmp_path):
    f = Fixture(tmp_path); f.transfer()
    f.gate['required_roles']['critical'] = f.author['id']; f.register('gate_requirements', f.gate)
    assert 'required_role_invalid' in f.assess()['reason_codes']
    del f.gate['required_roles']['critical']; f.register('gate_requirements', f.gate)
    assert 'required_role_missing' in f.assess()['reason_codes']


def test_revise_without_scoped_acceptance_requests_correction(tmp_path):
    f = Fixture(tmp_path, severity='optional')
    f.decision['next_action']['kind'] = 'revise'
    f.issue['blocking_scope'] = []; f.register('issues', f.issue)
    f.gate['decision_ref'] = f.register('decisions', f.decision)[0]; f.register('gate_requirements', f.gate)
    assert 'revise_binding_missing' in f.assess()['reason_codes']


def test_missing_acknowledgement_reuses_a06_validation(tmp_path):
    f = Fixture(tmp_path); f.transfer()
    f.decision['rationale_links'][0]['acknowledgement_refs'] = []
    f.gate['decision_ref'] = f.register('decisions', f.decision)[0]; f.register('gate_requirements', f.gate)
    assert 'position_ack_missing' in f.assess()['reason_codes']


def test_stale_transfer_acceptance_and_source_reference_rejected(tmp_path):
    f = Fixture(tmp_path); acceptance = f.transfer()
    f.register('transfer_acceptances', {**acceptance, 'accepted': False})
    assert 'transfer_acceptance_invalid' in f.assess()['reason_codes']
    f.gate['source_refs'][0] = {**f.source, 'artifact_id': 'missing'}; f.register('gate_requirements', f.gate)
    assert 'source_invalid' in f.assess()['reason_codes']


def test_gate_is_pure_and_bare_receipt_fails_closed(tmp_path, monkeypatch):
    f = Fixture(tmp_path); f.transfer()
    snapshot = commands.read_policy_snapshot(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('gate performed I/O')
    monkeypatch.setattr(store, '_history', forbidden); monkeypatch.setattr(store, '_read_file', forbidden)
    assert assess(snapshot, gate_id=f.gate['id'])['ready'] is True
    assert assess(f.head, gate_id=f.gate['id'])['reason_codes'] == ['gate_context_missing']


def test_duplicate_reviewer_actor_and_opaque_approval_receipt_rejected(tmp_path):
    f = Fixture(tmp_path); f.transfer()
    reviewer = f.reviewers['critical']
    f.register('assignments', {**reviewer, 'actor_id': 'domain'})
    assert 'required_role_invalid' in f.assess()['reason_codes']
    f.approval['existing_receipt_ref'] = f.source
    f.gate['approval_refs'] = f.register('approval_bindings', f.approval)
    f.register('gate_requirements', f.gate)
    assert 'approval_invalid' in f.assess()['reason_codes']


def test_forged_resolved_event_in_projection_cannot_hide_native_block(tmp_path):
    f = Fixture(tmp_path)
    # A backed forged event is still not a native issue.event transition.
    event = f.event('open', 'resolved')
    state = deepcopy(f.head['state']); state['issue_events'].append(event)
    state['issue_states'][f.issue['id']] = 'resolved'
    f.commit(state, {event['id']: store._canonical(event)})
    assert f.assess()['reason_codes'] == ['blocking_issue_unresolved']


def test_malformed_decision_fails_closed_without_exception(tmp_path):
    f = Fixture(tmp_path, severity='optional')
    f.decision['next_action'] = None
    f.gate['decision_ref'] = f.register('decisions', f.decision)[0]
    f.register('gate_requirements', f.gate)
    assert f.assess()['reason_codes'] == ['decision_invalid', 'required_submission_invalid', 'required_submission_missing']
