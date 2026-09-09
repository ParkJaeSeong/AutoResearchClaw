"""Synthetic B01 cited-item provenance fixtures; no source producer."""
from copy import deepcopy
import importlib
from uuid import uuid4

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.contracts import validate_record


def uid():
    return str(uuid4())


def group(snapshot):
    return importlib.import_module('researchclaw.core.research_graph.evidence_origins').group_origins(snapshot)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(root, topic='B01 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']

    def envelope(self):
        return {**store._VERSION, 'project_id': self.project, 'id': uid(), 'event_id': uid(),
            'producer_id': 'fixture', 'content_origin': 'synthetic',
            'provenance_status': 'declared_only', 'observation_refs': []}

    def commit(self, state, objects=None):
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(),
            state=state, event={**store._VERSION, 'type': 'synthetic_fixture', 'payload': {}}, objects=objects or {})

    def raw(self, name, content):
        self.commit(deepcopy(self.head['state']), {name: content})
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=name, sha256=store._hash(content))

    def register(self, collection, record, kind=None):
        if kind:
            assert validate_record(kind, record) == ()
        state = deepcopy(self.head['state']); state.setdefault(collection, {})[record['id']] = record
        self.commit(state, {f"{collection}/{record['id']}": store._canonical(record)})
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=record['id'],
                    sha256=store._hash(store._canonical(record)))

    def source(self, ref, **extra):
        return self.register('evidence_sources', {**self.envelope(), 'source_ref': ref, **extra})

    def edge(self, source, target, origin='dataset-A'):
        return self.register('dependencies', {**self.envelope(), 'from_ref': source, 'to_ref': target,
            'relation': 'derived_from', 'origin_group_id': origin}, 'Dependency')

    def check(self):
        snapshot = commands.read_policy_snapshot(self.root); before = deepcopy(snapshot)
        objects = {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()}
        try:
            return group(snapshot)
        finally:
            assert snapshot == before and store.read_head(self.root)['id'] == self.head['id']
            assert {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()} == objects


def test_three_papers_same_dataset_count_three_sources_one_origin(tmp_path):
    f = Fixture(tmp_path); dataset = f.raw('dataset', b'dataset')
    papers = [f.raw(f'paper-{i}', f'paper {i}'.encode()) for i in range(3)]
    for paper in papers:
        f.source(paper); f.edge(dataset, paper)
    result = f.check()
    assert result == {'source_count': 3, 'origin_group_count': 1,
        'origin_groups': [{'origin_group_id': 'dataset-A', 'source_refs': papers}],
        'unknown_refs': [], 'reason_codes': []}


@pytest.mark.parametrize('with_edge', [False, True])
def test_unknown_origin_is_preserved_and_never_counted_as_known(tmp_path, with_edge):
    f = Fixture(tmp_path); dataset = f.raw('dataset', b'd'); paper = f.raw('paper', b'p'); f.source(paper)
    if with_edge:
        f.edge(dataset, paper, 'unknown')
    assert f.check() == {'source_count': 1, 'origin_group_count': 0, 'origin_groups': [],
        'unknown_refs': [paper], 'reason_codes': ['origin_unknown']}


def test_downstream_known_label_does_not_erase_unknown_ancestry(tmp_path):
    f = Fixture(tmp_path); raw = f.raw('raw', b'r'); dataset = f.raw('dataset', b'd'); paper = f.raw('paper', b'p')
    f.edge(raw, dataset, 'unknown'); f.edge(dataset, paper); f.source(paper)
    result = f.check()
    assert result['origin_group_count'] == 1 and result['unknown_refs'] == [paper]
    assert result['reason_codes'] == ['origin_unknown']


def test_duplicate_source_registrations_and_group_links_do_not_inflate_counts(tmp_path):
    f = Fixture(tmp_path); dataset = f.raw('dataset', b'd'); paper = f.raw('paper', b'p')
    f.source(paper); later = {**paper, 'head_id': f.head['id']}; f.source(later)
    f.edge(dataset, paper); f.edge(dataset, later)
    result = f.check()
    assert result['source_count'] == 1 and result['origin_group_count'] == 1
    assert len(result['origin_groups'][0]['source_refs']) == 1


def test_missing_source_selection_is_distinct_from_explicit_empty(tmp_path):
    f = Fixture(tmp_path)
    with pytest.raises(ValueError, match='^evidence_sources_missing$'):
        f.check()
    state = deepcopy(f.head['state']); state['evidence_sources'] = {}; f.commit(state)
    assert f.check() == {'source_count': 0, 'origin_group_count': 0, 'origin_groups': [], 'unknown_refs': [], 'reason_codes': []}


def test_stale_cited_version_rejected_instead_of_counted_as_current(tmp_path):
    f = Fixture(tmp_path); paper = f.raw('paper', b'v1'); f.source(paper); f.raw('paper', b'v2')
    with pytest.raises(ValueError, match='^evidence_source_stale$'):
        f.check()


def test_historical_upstream_dataset_remains_exact(tmp_path):
    f = Fixture(tmp_path); dataset = f.raw('dataset', b'v1'); paper = f.raw('paper', b'p')
    f.edge(dataset, paper); f.source(paper); f.raw('dataset', b'v2')
    assert f.check()['origin_group_count'] == 1


def test_unrelated_unbacked_approval_does_not_become_origin_prerequisite(tmp_path):
    f = Fixture(tmp_path); paper = f.raw('paper', b'p'); f.source(paper)
    state = deepcopy(f.head['state']); state['approval_bindings'] = {uid(): {'invalid': True}}; f.commit(state)
    assert f.check()['source_count'] == 1


@pytest.mark.parametrize('field,value,reason', [('extra', True, 'evidence_source_invalid'),
    ('id', 'not-uuid', 'evidence_source_invalid'), ('content_origin', 'fiction', 'evidence_source_invalid'),
    ('head_id', 'hidden extra', 'evidence_source_invalid'),
    ('artifact_id', 'hidden extra', 'evidence_source_invalid'),
    ('sha256', 'hidden extra', 'evidence_source_invalid')])
def test_invalid_closed_source_record_rejected(tmp_path, field, value, reason):
    f = Fixture(tmp_path); paper = f.raw('paper', b'p'); f.source(paper, **{field: value})
    with pytest.raises(ValueError, match=f'^{reason}$'):
        f.check()


def test_unbacked_source_record_rejected(tmp_path):
    f = Fixture(tmp_path); paper = f.raw('paper', b'p'); f.source(paper)
    state = deepcopy(f.head['state']); next(iter(state['evidence_sources'].values()))['producer_id'] = 'unbacked'
    f.commit(state)
    with pytest.raises(ValueError, match='^issue_prerequisite_unbacked$'):
        f.check()


def test_unknown_upstream_reference_rejected_even_when_origin_label_unknown(tmp_path):
    f = Fixture(tmp_path); paper = f.raw('paper', b'p'); f.source(paper)
    f.edge({**paper, 'artifact_id': 'missing'}, paper, 'unknown')
    with pytest.raises(ValueError, match='^dependency_reference_invalid$'):
        f.check()


def test_cycle_rejected_even_in_unrelated_component(tmp_path):
    f = Fixture(tmp_path); paper = f.raw('paper', b'p'); other = f.raw('other', b'o'); f.source(paper)
    f.edge(paper, other); f.edge(other, paper)
    with pytest.raises(ValueError, match='^dependency_cycle$'):
        f.check()


def test_later_typed_uuid_collision_rejected_for_cited_source(tmp_path):
    f = Fixture(tmp_path); raw = f.raw('raw', b'r')
    verification = {**f.envelope(), 'issue_ids': [], 'method': 'calculation', 'question': 'Check',
        'input_refs': [raw], 'acceptance_rule': 'Exact', 'owner_assignment_id': uid(), 'budget_ref': raw}
    ref = f.register('verifications', verification, 'Verification'); f.source(ref)
    result = {**f.envelope(), 'id': verification['id'], 'verification_id': verification['id'],
        'output_refs': [raw], 'outcome': 'supported', 'checked_scope': ['Exact'], 'limitations': []}
    f.register('verification_results', result, 'VerificationResult')
    with pytest.raises(ValueError, match='^dependency_reference_ambiguous$'):
        f.check()
