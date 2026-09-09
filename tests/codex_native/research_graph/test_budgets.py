"""Synthetic A09 records; fixtures create no production prerequisite API."""
from copy import deepcopy
import importlib
import unicodedata
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import commands, store


def uid():
    return str(uuid4())


def assess(snapshot, payload):
    return importlib.import_module('researchclaw.core.research_graph.budgets').assess_next_work(snapshot, payload)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(root, topic='A09 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.owner = dict(id=uid(), project_id=self.project, actor_id='owner', role='owner', milestone='M2', active=True)
        self.register('assignments', self.owner)
        self.source = self.register('fixture_inputs', {**self.envelope(), 'text': 'fixed input'})[0]
        self.work = {**self.envelope(), 'assignment_id': self.owner['id'], 'milestone': 'M2', 'node': 'analysis',
            'question': 'Does RNA bind X?', 'input_refs': [self.source], 'work': 'Compare RNA effect', 'acceptance_rule': 'Effect above fixed bound'}
        self.resources = dict(returns=0, verification_runs=1, estimated_cost=2.0, cost_status='known')
        self.payload = dict(work=self.work, resource_request=self.resources, correction_ref=None,
                            correction_approval_ref=None, semantic_status='literal_only', resume_ref=None)
        self.ledger = dict(id=uid(), project_id=self.project, work_refs=[])
        self.register('work_ledgers', self.ledger)
        self.patch(work_ledger_id=self.ledger['id'])

    def envelope(self):
        return {**store._VERSION, 'id': uid(), 'project_id': self.project, 'event_id': uid(), 'producer_id': 'owner',
            'content_origin': 'synthetic', 'provenance_status': 'declared_only', 'observation_refs': []}

    def commit(self, state, objects=None):
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}}, objects=objects or {})

    def register(self, collection, *records):
        state = deepcopy(self.head['state']); state.setdefault(collection, {}).update({r['id']: r for r in records})
        self.commit(state, {r['id']: store._canonical(r) for r in records})
        return [dict(project_id=self.project, head_id=self.head['id'], artifact_id=r['id'], sha256=store._hash(store._canonical(r))) for r in records]

    def patch(self, **changes):
        self.commit({**self.head['state'], **changes})

    def prior(self, status='completed', correction_ref=None):
        record = dict(id=uid(), project_id=self.project, work=deepcopy(self.work), resource_request=deepcopy(self.resources), status=status, correction_ref=correction_ref)
        ref = self.register('work_records', record)[0]
        self.ledger['work_refs'].append(ref); self.register('work_ledgers', self.ledger)
        return record, ref

    def correction(self, previous_ref, evidence_refs=None):
        signature = {key: ' '.join(unicodedata.normalize('NFC', self.work[key]).split())
                     for key in ('milestone', 'node', 'question', 'work', 'acceptance_rule')}
        signature['input_refs'] = sorted([r['project_id'], r['artifact_id'], r['sha256']] for r in self.work['input_refs'])
        correction = dict(id=uid(), project_id=self.project, previous_work_ref=previous_ref,
            replacement_signature=store._hash(store._canonical(signature)), rationale='Correct an interpretation error', evidence_refs=evidence_refs if evidence_refs is not None else [self.source])
        ref = self.register('work_corrections', correction)[0]
        scope = [ref, previous_ref]
        receipt = dict(id=uid(), project_id=self.project, producer_id='existing-user-authority', decision='approved', binding=ref, scope_refs=scope)
        receipt_ref = self.register('approval_receipts', receipt)[0]
        approval = {**self.envelope(), 'existing_receipt_ref': receipt_ref, 'binding': ref, 'scope_refs': scope, 'validity': 'valid'}
        approval_ref = self.register('approval_bindings', approval)[0]
        self.payload.update(correction_ref=ref, correction_approval_ref=approval_ref)
        return correction, ref, approval

    def assess(self):
        return assess(commands.read_policy_snapshot(self.root), self.payload)


def test_first_work_with_backed_empty_ledger_ready_and_pure(tmp_path, monkeypatch):
    f = Fixture(tmp_path); snapshot = commands.read_policy_snapshot(tmp_path)
    before, payload = deepcopy(snapshot), deepcopy(f.payload)
    path = store._store_path(tmp_path) / 'objects' / f.source['sha256']; data = path.read_bytes()
    result = assess(snapshot, f.payload)
    assert result['ready'] is True and result['status'] == 'ready'
    assert result['reason_codes'] == [] and result['previous_status'] is None
    assert snapshot == before and f.payload == payload
    assert store.read_head(tmp_path)['id'] == f.head['id'] and path.read_bytes() == data
    def forbidden(*args, **kwargs):
        raise AssertionError('A09 performed I/O')
    monkeypatch.setattr(store, '_history', forbidden); monkeypatch.setattr(store, '_read_file', forbidden)
    assert assess(snapshot, f.payload) == result


def test_new_uuid_role_and_head_label_do_not_bypass_repeated_work(tmp_path):
    f = Fixture(tmp_path); f.prior()
    other = {**f.owner, 'id': uid(), 'actor_id': 'other'}; f.register('assignments', other)
    f.work.update(id=uid(), event_id=uid(), assignment_id=other['id'], producer_id='other')
    f.work['input_refs'] = [{**f.source, 'head_id': f.head['id']}]
    f.work['work'] = '  Compare   RNA effect  '
    result = f.assess()
    assert result['ready'] is False and result['status'] == 'awaiting_input'
    assert result['reason_codes'] == ['repeated_work']
    assert store.read_head(tmp_path)['id'] == f.head['id']


def test_scientific_case_is_preserved_and_explicit_semantic_uncertainty_waits(tmp_path):
    f = Fixture(tmp_path); f.prior()
    f.work['work'] = 'Compare rna effect'
    assert f.assess()['ready'] is True
    f.payload['semantic_status'] = 'uncertain'
    assert f.assess()['reason_codes'] == ['semantic_identity_uncertain']


@pytest.mark.parametrize('observed,estimate', [(None, 2), (1, None)])
def test_required_cost_limit_with_unknown_cost_awaits_input(tmp_path, observed, estimate):
    f = Fixture(tmp_path)
    f.patch(execution_cost_limit=10, observed_cost=observed, cost_status='unknown' if observed is None else 'known')
    f.resources.update(estimated_cost=estimate, cost_status='unknown' if estimate is None else 'known')
    result = f.assess()
    assert result['status'] == 'awaiting_input' and result['reason_codes'] == ['cost_unknown']


@pytest.mark.parametrize('state,resource_changes,reason', [({'returns_used': 3}, {'returns': 1}, 'returns_exhausted'),
    ({'verification_runs_used': 10}, {}, 'verification_runs_exhausted'),
    ({'execution_cost_limit': 10, 'observed_cost': 9, 'cost_status': 'known'}, {}, 'execution_cost_exhausted')])
def test_separate_budget_limits_block_only_requested_resource(tmp_path, state, resource_changes, reason):
    f = Fixture(tmp_path); f.patch(**state); f.resources.update(resource_changes)
    result = f.assess()
    assert result['ready'] is False and result['status'] == 'blocked_budget'
    assert result['reason_codes'] == [reason]


def test_unused_return_limit_does_not_block_run(tmp_path):
    f = Fixture(tmp_path); f.patch(returns_used=3)
    assert f.assess()['ready'] is True


def test_exact_approved_correction_allows_one_retry_but_not_reuse(tmp_path):
    f = Fixture(tmp_path); _, prior = f.prior('failed')
    _, correction_ref, _ = f.correction(prior)
    assert f.assess()['ready'] is True
    f.prior('failed', correction_ref=correction_ref)
    f.payload['correction_ref'] = {**correction_ref, 'head_id': f.head['id']}
    result = f.assess()
    assert result['ready'] is False and 'correction_already_used' in result['reason_codes']


@pytest.mark.parametrize('fault', ['revoked', 'wrong_work', 'wrong_signature', 'missing_approval'])
def test_correction_requires_current_exact_prior_work_and_approval(tmp_path, fault):
    f = Fixture(tmp_path); _, prior = f.prior('failed')
    correction, ref, approval = f.correction(prior)
    if fault == 'revoked':
        approval['validity'] = 'revoked'; f.payload['correction_approval_ref'] = f.register('approval_bindings', approval)[0]
    elif fault == 'missing_approval':
        f.payload['correction_approval_ref'] = None
    else:
        correction['previous_work_ref' if fault == 'wrong_work' else 'replacement_signature'] = f.source if fault == 'wrong_work' else 'a' * 64
        f.payload['correction_ref'] = f.register('work_corrections', correction)[0]
    assert f.assess()['ready'] is False
    assert 'correction_invalid' in f.assess()['reason_codes']


def test_correction_never_bypasses_budget_and_resume_preserves_failed_outcome(tmp_path):
    f = Fixture(tmp_path); _, prior = f.prior('failed'); f.correction(prior)
    f.payload['resume_ref'] = prior; f.patch(verification_runs_used=10)
    result = f.assess()
    assert result['status'] == 'blocked_budget' and result['previous_status'] == 'failed'
    assert result['reason_codes'] == ['verification_runs_exhausted']
    assert result['next_actions'] and store.read_head(tmp_path)['state']['work_records'][prior['artifact_id']]['status'] == 'failed'


def test_missing_ledger_and_omitted_history_fail_closed(tmp_path):
    f = Fixture(tmp_path); f.patch(work_ledger_id=None)
    assert f.assess()['reason_codes'] == ['work_ledger_invalid']
    f.patch(work_ledger_id=f.ledger['id']); f.prior()
    f.ledger['work_refs'] = []; f.register('work_ledgers', f.ledger)
    assert f.assess()['reason_codes'] == ['work_ledger_invalid']


@pytest.mark.parametrize('field,value', [('verification_runs', True), ('estimated_cost', float('nan')), ('returns', -1)])
def test_invalid_resource_values_fail_closed(tmp_path, field, value):
    f = Fixture(tmp_path); f.resources[field] = value
    assert f.assess()['reason_codes'] == ['resource_request_invalid']


def test_changed_input_revision_is_new_work_without_reinterpreting_history(tmp_path):
    f = Fixture(tmp_path); f.prior()
    source = {**f.head['state']['fixture_inputs'][f.source['artifact_id']], 'text': 'new observation'}
    f.work['input_refs'] = f.register('fixture_inputs', source)
    assert f.assess()['ready'] is True


def test_bare_snapshot_and_malformed_collections_fail_closed(tmp_path):
    f = Fixture(tmp_path)
    assert assess(f.head, f.payload)['reason_codes'] == ['work_context_missing']
    f.patch(work_records=None)
    assert f.assess()['reason_codes'] == ['work_collection_invalid']


def test_boolean_schema_version_is_rejected_without_head_change(tmp_path):
    f = Fixture(tmp_path); f.work['schema_version'] = True
    before = store.read_head(tmp_path)
    assert f.assess()['reason_codes'] == ['work_invalid']
    assert store.read_head(tmp_path) == before


def test_historical_nonnull_correction_ref_requires_exact_valid_binding(tmp_path):
    f = Fixture(tmp_path); f.prior(correction_ref='not-a-reference')
    f.work['work'] = 'Check a different consequence'
    before = store.read_head(tmp_path)
    assert f.assess()['reason_codes'] == ['work_ledger_invalid']
    assert store.read_head(tmp_path) == before


def test_used_correction_clone_with_duplicate_evidence_cannot_authorize_retry(tmp_path):
    f = Fixture(tmp_path); _, previous = f.prior('failed')
    _, correction_ref, _ = f.correction(previous)
    f.prior('failed', correction_ref=correction_ref)
    f.correction(previous, evidence_refs=[f.source, f.source])
    before = store.read_head(tmp_path)
    result = f.assess()
    assert result['ready'] is False
    assert result['reason_codes'] == ['correction_invalid', 'repeated_work']
    assert store.read_head(tmp_path) == before
