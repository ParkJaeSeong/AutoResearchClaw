"""B04 synthetic native baseline copied per test; no actual user approval."""
from copy import deepcopy
import importlib
import json
import shutil

import pytest

from researchclaw.core.research_graph import commands, store
from tests.codex_native.research_graph.test_m1_scope import Fixture as ScopeFixture, uid


def api():
    return importlib.import_module('researchclaw.core.research_graph.m1_search')


class Fixture(ScopeFixture):
    def node(self, name='scope', **changes):
        artifact = super().node(name, **changes)
        if name == 'search':
            artifact['content'] = {'queries': ['method replication'], 'sources': ['Open index'],
                'inclusion_criteria': ['Direct comparison'], 'exclusion_criteria': ['Unrelated task']}
        elif name == 'screen':
            artifact['content'] = {
                'search_log': [{'search_id': 'search-1', 'query': 'method replication', 'source': 'Open index',
                                'searched_at': '2026-09-09T00:00:00Z', 'result_count': 2}],
                'candidates': [dict(source_id=f'paper-{i}', title=f'Comparison paper {i}', doi=f'10.1000/paper{i}',
                    arxiv_id=None, url=None, source_type='paper', access_status='abstract', search_ids=['search-1'],
                    stance='support' if i == 1 else 'oppose') for i in (1, 2)],
                'decisions': [dict(source_id=f'paper-{i}', decision='include', reason='Addresses the comparison') for i in (1, 2)]}
        if 'content' in changes:
            artifact['content'] = changes['content']
        return artifact

    def check(self, node=None):
        name = node or self.artifact['node']
        if name not in ('search', 'screen'):
            return super().check(name)
        snapshot = self.snapshot(); before = deepcopy(snapshot)
        try:
            return api().prepare_search_council(snapshot, node_id=name)
        finally:
            assert snapshot == before and store.read_head(self.root)['id'] == self.head['id']

    def decide(self, decision='approve', corpus_ref=None, command_id=None):
        identity = uid()
        result = self.apply('m1.corpus.decide', dict(receipt_id=identity,
            corpus_ref=corpus_ref or self.check()['corpus_ref'], decision=decision, note='Synthetic explicit user declaration'), command_id=command_id)
        record = result['state']['approval_receipts'][identity]
        return dict(project_id=self.project, head_id=result['id'], artifact_id=identity, sha256=store._hash(store._canonical(record)))

    def bind(self, receipt):
        identity = uid()
        result = self.apply('m1.corpus.bind', dict(binding_id=identity, event_id=uid(), receipt_ref=receipt))
        record = result['state']['approval_bindings'][identity]
        return dict(project_id=self.project, head_id=result['id'], artifact_id=identity, sha256=store._hash(store._canonical(record)))


@pytest.fixture(scope='module')
def native_baseline(tmp_path_factory):
    root = tmp_path_factory.mktemp('b04-native') / 'project'
    f = Fixture(root); f.register(); f.council_prepare(); f.complete(); scope = f.check()['node_ref']
    f.register(f.node('questions', input_refs={'scope': scope})); f.council_prepare(); f.complete(); questions = f.check()['node_ref']
    f.register(f.node('search', input_refs={'scope': scope, 'questions': questions})); f.council_prepare(); f.complete(); search = f.check()['node_ref']
    f.register(f.node('screen', input_refs={'scope': scope, 'questions': questions, 'search': search}))
    f.council_prepare(); f.complete()
    return root


@pytest.fixture
def f(native_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(native_baseline, root)
    fixture = Fixture.__new__(Fixture); fixture.root = root; fixture.head = store.read_head(root)
    state = fixture.head['state']; fixture.project = state['project_id']
    artifact = deepcopy(state['m1_node_revisions'][state['m1_node_heads']['screen']])
    artifact['previous_ref'] = json.loads(artifact.pop('previous_ref_key')) if artifact['previous_ref_key'] else None
    artifact.pop('previous_ref_key', None)
    fixture.artifact = artifact
    fixture.council = next(c for c in state['councils'].values() if c['attempt'] == artifact['attempt'])
    fixture.session = state['review_sessions'][fixture.council['session_id']]
    fixture.binding = fixture.session['input_binding']
    fixture.author = state['assignments'][fixture.council['author_assignment_ids'][0]]
    fixture.reviewers = [state['assignments'][fixture.council['required_roles'][role]] for role in ('domain', 'methodology', 'critical')]
    return fixture


def test_real_screen_consensus_waits_for_explicit_user_corpus_approval(f):
    result = f.check()
    assert result['review_ready'] is True and result['ready'] is False
    assert result['approved'] is False and result['reason_codes'] == ['corpus_approval_required']
    assert result['approval_ref'] is None and result['next_node'] is None


def test_explicit_prior_user_receipt_then_derived_binding_covers_complete_corpus(f):
    receipt = f.decide(); assert f.check()['approved'] is False
    approval = f.bind(receipt); result = f.check()
    assert result['ready'] is True and result['approved'] is True and result['approval_ref'] == approval
    corpus = api().current_corpus(f.snapshot())
    assert len(corpus['scope_refs']) == 4 and {r['artifact_id'] for r in corpus['scope_refs']} == {
        'm1/nodes/scope', 'm1/nodes/questions', 'm1/nodes/search', 'm1/nodes/screen'}
    assert {s['source_id'] for s in corpus['kept_sources']} == {'paper-1', 'paper-2'}
    binding = f.head['state']['approval_bindings'][approval['artifact_id']]
    assert binding['binding'] == corpus['corpus_ref'] and binding['scope_refs'] == corpus['scope_refs']


def test_latest_reject_revokes_binding_and_preserves_old_approved_bytes(f):
    receipt = f.decide(); approval = f.bind(receipt)
    path = store._store_path(f.root) / 'objects' / approval['sha256']; old = path.read_bytes()
    f.decide('reject')
    assert f.check()['approved'] is False and f.check()['reason_codes'] == ['corpus_rejected']
    assert f.head['state']['approval_bindings'][approval['artifact_id']]['validity'] == 'revoked'
    assert path.read_bytes() == old
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_corpus_receipt_not_current$'):
        f.bind(receipt)
    assert store.read_head(f.root)['id'] == head


def test_changed_corpus_requires_new_user_decision(f):
    receipt = f.decide(); approval = f.bind(receipt); prior = f.check()['corpus_ref']
    content = deepcopy(f.artifact['content']); content['decisions'][0]['reason'] = 'New explicit selection rationale'
    f.register(f.node('screen', previous_ref=prior, revision_reason='Revise corpus selection rationale',
        input_refs=f.artifact['input_refs'], content=content))
    f.council_prepare(); f.complete()
    assert f.check()['reason_codes'] == ['corpus_approval_required']
    assert f.check()['approval_ref'] is None
    with pytest.raises(ValueError, match='^m1_corpus_changed$'):
        f.bind(receipt)
    assert f.head['state']['approval_bindings'][approval['artifact_id']]['binding'] == prior


def test_renewed_approval_requires_new_binding_and_never_revives_revoked_one(f):
    old = f.bind(f.decide()); f.decide('reject'); renewed = f.decide()
    assert f.check()['approved'] is False
    new = f.bind(renewed)
    assert f.check()['approval_ref'] == new
    assert f.head['state']['approval_bindings'][old['artifact_id']]['validity'] == 'revoked'


def test_excluded_opposing_source_requires_native_issue_even_after_ready_votes(f):
    prior = f.check()['corpus_ref']; content = deepcopy(f.artifact['content'])
    content['decisions'][1] = dict(source_id='paper-2', decision='exclude', reason='Declared relevance concern')
    f.register(f.node('screen', previous_ref=prior, revision_reason='Review opposing-source exclusion',
        input_refs=f.artifact['input_refs'], content=content))
    f.council_prepare(); f.complete()
    assert 'opposing_exclusion_issue_required' in f.check()['reason_codes']
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_corpus_review_required$'):
        f.decide()
    assert store.read_head(f.root)['id'] == head
    issue = f.issue(); issue['category'] = 'source'; issue['origin']['local_issue_id'] = 'opposing-exclusion/paper-2'
    f.publish(issue)
    result = f.check()
    assert 'opposing_exclusion_issue_required' not in result['reason_codes']
    assert 'blocking_issue_unresolved' in result['reason_codes']


@pytest.mark.parametrize('fault', ['unknown_search_id', 'missing_candidate_decision', 'duplicate_source', 'extra_field'])
def test_invalid_screening_provenance_refused_and_head_preserved(f, fault):
    prior = f.check()['corpus_ref']; content = deepcopy(f.artifact['content'])
    if fault == 'unknown_search_id': content['candidates'][0]['search_ids'] = ['not-logged']
    if fault == 'missing_candidate_decision': content['decisions'].pop()
    if fault == 'duplicate_source': content['candidates'].append(deepcopy(content['candidates'][0]))
    if fault == 'extra_field': content['candidates'][0]['approved'] = True
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_(node_invalid|search_content_invalid)$'):
        f.register(f.node('screen', previous_ref=prior, revision_reason='Invalid test update',
            input_refs=f.artifact['input_refs'], content=content))
    assert store.read_head(f.root)['id'] == head


def test_unreviewed_questions_prevent_actual_search_registration(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete(); scope = f.check()['node_ref']
    f.register(f.node('questions', input_refs={'scope': scope})); questions = f.check()['node_ref']; head = f.head['id']
    with pytest.raises(ValueError, match='^m1_upstream_review_required$'):
        f.register(f.node('search', input_refs={'scope': scope, 'questions': questions}))
    assert store.read_head(tmp_path)['id'] == head


def test_receipt_without_native_user_decision_cannot_create_approval(f):
    corpus = api().current_corpus(f.snapshot()); identity = uid()
    receipt = dict(id=identity, project_id=f.project, producer_id='user', decision='approved',
        binding=corpus['corpus_ref'], scope_refs=corpus['scope_refs'])
    state = deepcopy(f.head['state']); state.setdefault('approval_receipts', {})[identity] = receipt
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_imported_receipt', 'payload': {}}, objects={identity: store._canonical(receipt)})
    ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=identity, sha256=store._hash(store._canonical(receipt)))
    with pytest.raises(ValueError, match='^m1_corpus_receipt_invalid$'):
        f.bind(ref)
    assert f.check()['approved'] is False


def test_malformed_receipt_collection_is_refused_without_head_change(f):
    receipt = f.decide(); state = deepcopy(f.head['state']); state['approval_receipts'] = []
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_malformed_receipts', 'payload': {}}, objects={})
    head = f.head['id']
    with pytest.raises(ValueError, match='^dependency_collection_invalid$'):
        f.bind(receipt)
    assert store.read_head(f.root)['id'] == head


def test_native_decision_replay_is_idempotent_and_conflicting_retry_preserves_head(f):
    command_id = uid(); before = f.head['id']
    payload = dict(receipt_id=uid(), corpus_ref=f.check()['corpus_ref'], decision='approve', note='Synthetic explicit user choice')
    result = f.apply('m1.corpus.decide', payload, command_id=command_id)
    head = f.head['id']
    assert f.apply('m1.corpus.decide', payload, command_id=command_id, expected_head=before) == result
    with pytest.raises(ValueError, match='^research_graph_command_conflict$'):
        f.apply('m1.corpus.decide', {**payload, 'decision': 'reject'}, command_id=command_id, expected_head=before)
    assert store.read_head(f.root)['id'] == head


def test_user_can_reject_historical_corpus_after_replacement_without_new_review(f):
    approval = f.bind(f.decide()); prior = f.check()['corpus_ref']
    f.register(f.node('screen', previous_ref=prior, revision_reason='Start a new corpus revision', input_refs=f.artifact['input_refs']))
    assert f.check()['review_ready'] is False
    f.decide('reject', corpus_ref=prior)
    assert f.head['state']['approval_bindings'][approval['artifact_id']]['validity'] == 'revoked'
    assert f.check()['approved'] is False
