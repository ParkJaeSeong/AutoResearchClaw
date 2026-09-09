"""Synthetic dependency policy fixtures; no approval or research producers."""
from copy import deepcopy
import importlib
from uuid import uuid4

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.contracts import validate_record


def uid():
    return str(uuid4())


def key(ref):
    return store._canonical(ref).decode()


def plan(snapshot, changed):
    return importlib.import_module('researchclaw.core.research_graph.dependencies').plan_revalidation(
        snapshot, changed_refs=changed)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(root, topic='A08 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']

    def envelope(self):
        return {**store._VERSION, 'project_id': self.project, 'id': uid(), 'event_id': uid(),
                'producer_id': 'fixture', 'content_origin': 'synthetic',
                'provenance_status': 'declared_only', 'observation_refs': []}

    def commit(self, state, objects):
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(),
            state=state, event={**store._VERSION, 'type': 'synthetic_fixture', 'payload': {}}, objects=objects)

    def raw(self, name, content):
        self.commit(deepcopy(self.head['state']), {name: content})
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=name, sha256=store._hash(content))

    def register(self, collection, record, kind=None):
        if kind:
            assert validate_record(kind, record) == ()
        state = deepcopy(self.head['state'])
        state.setdefault(collection, {})[record['id']] = record
        self.commit(state, {f"{collection}/{record['id']}": store._canonical(record)})
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=record['id'],
                    sha256=store._hash(store._canonical(record)))

    def edge(self, source, target, relation='supports'):
        return self.register('dependencies', {**self.envelope(), 'from_ref': source, 'to_ref': target,
            'relation': relation, 'origin_group_id': 'unknown'}, 'Dependency')

    def approval(self, binding, scope=None, validity='valid', receipt_decision='approved'):
        scope = [binding] if scope is None else scope
        receipt = self.register('approval_receipts', dict(id=uid(), project_id=self.project,
            producer_id='existing-authority', decision=receipt_decision, binding=binding, scope_refs=scope))
        record = {**self.envelope(), 'existing_receipt_ref': receipt, 'binding': binding,
                  'scope_refs': scope, 'validity': validity}
        return self.register('approval_bindings', record, 'ApprovalBinding')

    def snapshot(self):
        return commands.read_policy_snapshot(self.root)

    def check(self, changed):
        snapshot = self.snapshot()
        before = deepcopy(snapshot)
        objects = {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()}
        try:
            return plan(snapshot, changed)
        finally:
            assert snapshot == before
            assert store.read_head(self.root)['id'] == self.head['id']
            assert {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()} == objects


def test_analysis_change_only_affects_descendants_and_reuses_unrelated_approval(tmp_path):
    f = Fixture(tmp_path)
    analysis = f.raw('analysis', b'old analysis'); chart = f.raw('chart', b'chart')
    claim = f.raw('claim', b'claim'); literature = f.raw('literature', b'source')
    f.edge(analysis, chart, 'derived_from'); f.edge(chart, claim, 'supports')
    final_approval = f.approval(claim); literature_approval = f.approval(literature)
    f.raw('analysis', b'new analysis')
    result = f.check([key(analysis)])
    assert {key(r) for r in result['affected_refs']} == {key(analysis), key(chart), key(claim)}
    checks = {c['approval_ref']['artifact_id']: c for c in result['approval_checks']}
    assert checks[final_approval['artifact_id']]['reason_codes'] == ['needs_revalidation']
    assert checks[literature_approval['artifact_id']]['reusable'] is True
    assert {r['artifact_id'] for r in result['reusable_refs']} == {literature_approval['artifact_id']}
    assert result['event_plan'] == {**store._VERSION, 'type': 'needs_revalidation', 'payload': {
        'changed_refs': [analysis], 'affected_refs': result['affected_refs'], 'approval_refs': [final_approval]}}


@pytest.mark.parametrize('relation', ['supports', 'derived_from', 'tests', 'reports'])
def test_each_relation_traverses_downstream_only(tmp_path, relation):
    f = Fixture(tmp_path); source = f.raw('source', b's'); target = f.raw('target', b't')
    f.edge(source, target, relation)
    result = f.check([key(target)])
    assert result['affected_refs'] == [target]
    assert result['reusable_refs'] == [source]


def test_same_version_at_later_head_connects_but_new_digest_does_not(tmp_path):
    f = Fixture(tmp_path); old = f.raw('analysis', b'v1'); chart = f.raw('chart', b'chart')
    later = {**old, 'head_id': f.head['id']}
    f.edge(later, chart)
    new = f.raw('analysis', b'v2'); new_chart = f.raw('new-chart', b'new chart')
    f.edge(new, new_chart)
    result = f.check([key(old)])
    assert {r['artifact_id'] for r in result['affected_refs']} == {'analysis', 'chart'}
    assert {r['sha256'] for r in result['affected_refs']} == {old['sha256'], chart['sha256']}


def test_scope_without_dependency_edge_requires_approval_review(tmp_path):
    f = Fixture(tmp_path); binding = f.raw('packet', b'p'); source = f.raw('source', b's')
    approval = f.approval(binding, [binding, source])
    result = f.check([key(source)])
    assert result['approval_checks'] == [{'approval_ref': approval, 'reason_codes': ['needs_revalidation'], 'reusable': False}]
    assert result['event_plan']['payload']['approval_refs'] == [approval]


def test_dependency_to_approval_itself_requires_review(tmp_path):
    f = Fixture(tmp_path); binding = f.raw('packet', b'p'); source = f.raw('source', b's')
    approval = f.approval(binding)
    f.edge(source, approval)
    result = f.check([key(source)])
    assert result['approval_checks'][0]['reason_codes'] == ['needs_revalidation']
    assert result['event_plan']['payload']['approval_refs'] == [approval]
    assert result['reusable_refs'] == []


def test_revoked_approval_dag_node_is_not_generic_reusable_object(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's'); approval = f.approval(source, validity='revoked')
    f.edge(source, approval)
    result = f.check([])
    assert result['reusable_refs'] == [source]


@pytest.mark.parametrize('validity', ['revoked', 'expired', 'unknown', 'needs_revalidation'])
def test_noncurrent_approval_is_never_reused(tmp_path, validity):
    f = Fixture(tmp_path); source = f.raw('source', b's'); approval = f.approval(source, validity=validity)
    result = f.check([])
    assert result['approval_checks'] == [{'approval_ref': approval, 'reason_codes': ['approval_not_current'], 'reusable': False}]
    assert result['reusable_refs'] == [] and result['event_plan'] is None


def test_stale_unaffected_scope_is_not_reused(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b'v1'); f.approval(source)
    f.raw('source', b'v2')
    assert f.check([])['approval_checks'][0]['reason_codes'] == ['approval_not_current']


def test_rejected_receipt_fails_closed(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's'); f.approval(source, receipt_decision='rejected')
    with pytest.raises(ValueError, match='^dependency_approval_invalid$'):
        f.check([])


def test_unbacked_receipt_fails_closed(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's'); f.approval(source)
    state = deepcopy(f.head['state'])
    next(iter(state['approval_receipts'].values()))['producer_id'] = 'unbacked replacement'
    f.commit(state, {})
    with pytest.raises(ValueError, match='^issue_reference_stale$'):
        f.check([])


@pytest.mark.parametrize('collection', ['dependencies', 'approval_bindings', 'approval_receipts', 'verifications'])
def test_malformed_collection_fails_closed(tmp_path, collection):
    f = Fixture(tmp_path); state = deepcopy(f.head['state']); state[collection] = []
    f.commit(state, {})
    with pytest.raises(ValueError, match='^dependency_collection_invalid$'):
        f.check([])


def test_unknown_dependency_endpoint_rejected_even_outside_impact(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's')
    f.edge(source, {**source, 'artifact_id': 'unknown'})
    with pytest.raises(ValueError, match='^dependency_reference_invalid$'):
        f.check([])


def test_corrupted_referenced_bytes_rejected(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's'); snapshot = f.snapshot()
    snapshot['_issue_context']['objects'][source['sha256']] = b'corruption'
    with pytest.raises(ValueError, match='^dependency_reference_invalid$'):
        plan(snapshot, [key(source)])


def test_same_digest_different_artifact_stays_separate(tmp_path):
    f = Fixture(tmp_path); a = f.raw('a', b'same'); b = f.raw('b', b'same'); target = f.raw('target', b't')
    f.edge(b, target)
    result = f.check([key(a)])
    assert result['affected_refs'] == [a]
    assert {r['artifact_id'] for r in result['reusable_refs']} == {'b', 'target'}


def test_cycle_across_later_head_aliases_rejected(tmp_path):
    f = Fixture(tmp_path); a = f.raw('a', b'a'); b = f.raw('b', b'b')
    later = {**a, 'head_id': f.head['id']}
    f.edge(a, b); f.edge(b, later)
    with pytest.raises(ValueError, match='^dependency_cycle$'):
        f.check([])


@pytest.mark.parametrize('mutation', ['artifact_id', 'sha256', 'head_id', 'project_id'])
def test_unknown_exact_reference_rejected_and_head_preserved(tmp_path, mutation):
    f = Fixture(tmp_path); ref = f.raw('source', b's')
    ref[mutation] = uid() if mutation in ('artifact_id', 'project_id') else 'f' * 64
    with pytest.raises(ValueError, match='^dependency_reference_invalid$'):
        f.check([key(ref)])


@pytest.mark.parametrize('changed', [['source'], ['{}'], [1], 'source'])
def test_noncanonical_changed_ref_rejected(tmp_path, changed):
    f = Fixture(tmp_path)
    with pytest.raises(ValueError, match='^dependency_changed_refs_invalid$'):
        f.check(changed)


def test_typed_verification_uuid_resolves_namespaced_object_alias(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's'); chart = f.raw('chart', b'c')
    verification = {**f.envelope(), 'issue_ids': [], 'method': 'calculation', 'question': 'Check arithmetic',
        'input_refs': [source], 'acceptance_rule': 'Exact equality', 'owner_assignment_id': uid(), 'budget_ref': source}
    ref = f.register('verifications', verification, 'Verification')
    f.edge(source, ref, 'tests'); f.edge(ref, chart, 'reports')
    assert {r['artifact_id'] for r in f.check([key(source)])['affected_refs']} == {'source', verification['id'], 'chart'}


def test_missing_verified_context_fails_closed(tmp_path):
    f = Fixture(tmp_path)
    with pytest.raises(ValueError, match='^issue_context_missing$'):
        plan(store.read_head(tmp_path), [])


def test_later_typed_id_collision_rejected_instead_of_reusing_historical_ref(tmp_path):
    f = Fixture(tmp_path); source = f.raw('source', b's')
    verification = {**f.envelope(), 'issue_ids': [], 'method': 'calculation', 'question': 'Check arithmetic',
        'input_refs': [source], 'acceptance_rule': 'Exact equality', 'owner_assignment_id': uid(), 'budget_ref': source}
    ref = f.register('verifications', verification, 'Verification')
    f.edge(source, ref, 'tests')
    result = {**f.envelope(), 'id': verification['id'], 'verification_id': verification['id'],
        'output_refs': [source], 'outcome': 'supported', 'checked_scope': ['Exact equality'], 'limitations': []}
    f.register('verification_results', result, 'VerificationResult')
    with pytest.raises(ValueError, match='^dependency_reference_ambiguous$'):
        f.check([])
