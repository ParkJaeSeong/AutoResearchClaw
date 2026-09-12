"""B06 native synthetic review chain; source checks cached once per module."""
from copy import deepcopy
import importlib
import shutil

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.m1_nodes import _context, current_node, review_node
from tests.codex_native.research_graph.test_m1_evidence import (
    Fixture as EvidenceFixture, collected_baseline, load, native_baseline)


def api():
    return importlib.import_module('researchclaw.core.research_graph.m1_review')


class Fixture(EvidenceFixture):
    def check(self, node=None):
        node = node or self.artifact['node']
        if node in ('synthesize', 'hypothesize', 'review'):
            return review_node(self.snapshot(), node)
        return super().check(node)

    def council_payload(self, **kwargs):
        payload = super().council_payload(**kwargs)
        if self.artifact['node'] == 'review':
            payload['council']['issue_ids'] = [row['issue_id'] for row in api()._prior_issues(_context(self.snapshot()))]
        return payload

    def make(self, node, **changes):
        evidence = importlib.import_module('researchclaw.core.research_graph.m1_evidence').current_evidence(self.snapshot())
        refs = list(evidence['extraction_refs'].values())
        parents = {'synthesize': ('screen', 'collect', 'extract'),
                   'hypothesize': ('screen', 'extract', 'synthesize'),
                   'review': ('screen', 'extract', 'synthesize', 'hypothesize')}[node]
        inputs = _context(self.snapshot())
        content = {
            'synthesize': dict(findings=[dict(finding_id='finding-1', claim='A recorded value appears in two papers',
                evidence_refs=refs, counterevidence_refs=[], limitations=['One underlying dataset'])],
                rejected_alternatives=[dict(alternative_id='alt-1', description='Independent replications',
                    reason='Both papers use the same dataset', evidence_refs=refs)], limitations=[]),
            'hypothesize': dict(hypotheses=[dict(hypothesis_id='H1', statement='The gain depends on population composition',
                population='Prespecified groups', prediction='Within-group gains differ',
                falsification_condition='No within-group gain under the fixed comparison', evidence_refs=refs,
                alternative_ids=['alt-1'], limitations=['Not empirically tested'])], limitations=[]),
            'review': dict(prior_issue_dispositions=[], open_questions=[], limitations=['No experiments executed'])}[node]
        return self.node(node, input_refs={name: current_node(inputs, name)[1] for name in parents},
                         **{'content': content, **changes})

    def chain(self, through='review', complete=True):
        for node in ('synthesize', 'hypothesize', 'review'):
            self.register(self.make(node))
            if complete:
                self.council_prepare(); self.complete()
            if node == through:
                break


@pytest.fixture(scope='module')
def extracted_baseline(collected_baseline, tmp_path_factory):
    root = tmp_path_factory.mktemp('b06-extracted') / 'project'; shutil.copytree(collected_baseline, root)
    f = load(root, 'collect'); f.extract(); f.setup(); f.result_and_resolution(f.observe())
    assert importlib.import_module('researchclaw.core.research_graph.m1_evidence').current_evidence(f.snapshot())['ready']
    return root


@pytest.fixture
def f(extracted_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(extracted_baseline, root)
    f = load(root, 'extract'); f.__class__ = Fixture
    return f


def test_native_complete_review_preserves_evidence_origins_and_exact_bytes(f):
    before = f.snapshot()['_issue_context']['objects'].copy()
    f.chain('hypothesize')
    from researchclaw.core.research_graph.gates import _status
    inputs = _context(f.snapshot())
    issue = next(issue for issue in inputs.state['issues'].values() if issue['origin']['node'] == 'extract')
    status, event = _status(inputs, issue)
    assert status == 'resolved'
    artifact = f.make('review')
    artifact['content']['prior_issue_dispositions'] = [dict(issue_id=issue['id'], disposition='native_resolved',
        owner_assignment_id=issue['owner_assignment_id'], hypothesis_ids=['H1'], rationale='Native independent source check',
        verification_refs=event['verification_refs'])]
    f.register(artifact); f.council_prepare(); f.complete()
    snapshot = f.snapshot(); unchanged = deepcopy(snapshot)
    result = api().prepare_hypothesis_review(snapshot)
    assert result['ready'] is True and result['reason_codes'] == []
    from researchclaw.core.research_graph.handoffs import _require_native_evidence_route
    _require_native_evidence_route(_context(snapshot))
    assert result['phase'] == 'complete' and result['source_groups']['origin_group_count'] == 1
    assert result['source_groups']['source_count'] == 2 and result['limitations']
    assert not result['unaccounted_issue_ids']
    assert snapshot == unchanged and store.read_head(f.root)['id'] == f.head['id']
    assert all(snapshot['_issue_context']['objects'][key] == value for key, value in before.items())


def test_r2_empty_new_issues_cannot_erase_unaccounted_prior_issue_and_repair_is_allowed(f):
    f.chain('hypothesize'); issue = f.issue(); issue['blocking_scope'] = []; f.publish(issue)
    f.register(f.make('review')); f.council_prepare(); f.complete()
    prior = f.check()['node_ref']; old = store._canonical(f.head['state']['m1_node_revisions'][f.artifact['id']])
    f.register(f.make('review', previous_ref=prior, revision_reason='Second review has no new issues'))
    result = api().prepare_hypothesis_review(f.snapshot())
    assert 'prior_issue_unaccounted' in result['reason_codes']
    assert result['unaccounted_issue_ids'] == [issue['id']]
    assert result['unresolved_issue_ids'] == [issue['id']]
    assert f.snapshot()['_issue_context']['objects'][store._hash(old)] == old


def test_hypothesis_revision_is_not_native_resolution(f):
    f.chain('hypothesize'); issue = f.issue(); f.publish(issue)
    prior = f.check()['node_ref']
    f.register(f.make('hypothesize', previous_ref=prior, revision_reason='Clarify falsification'))
    disposition = dict(issue_id=issue['id'], disposition='native_resolved', owner_assignment_id=issue['owner_assignment_id'],
        hypothesis_ids=['H1'], rationale='The hypothesis changed', verification_refs=[])
    artifact = f.make('review'); artifact['content']['prior_issue_dispositions'] = [disposition]
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_review_resolution_invalid$'):
        f.register(artifact)
    assert store.read_head(f.root)['id'] == head


def test_incomplete_council_and_missing_evidence_never_ready(f):
    f.chain(complete=False)
    result = api().prepare_hypothesis_review(f.snapshot())
    assert result['ready'] is False and 'council_required' in result['reason_codes']
    f.decide('reject', corpus_ref=result['corpus_ref'])
    assert api().prepare_hypothesis_review(f.snapshot())['ready'] is False


@pytest.mark.parametrize('fault', ['unrelated_evidence', 'unknown_alternative', 'extra_content'])
def test_closed_scientific_content_rejects_invalid_links_and_preserves_head(f, fault):
    f.chain('synthesize', complete=False)
    artifact = f.make('hypothesize')
    if fault == 'unrelated_evidence': artifact['content']['hypotheses'][0]['evidence_refs'] = [artifact['input_refs']['screen']]
    if fault == 'unknown_alternative': artifact['content']['hypotheses'][0]['alternative_ids'] = ['missing']
    if fault == 'extra_content': artifact['content']['ready'] = True
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_(review_evidence_invalid|review_alternative_invalid|node_invalid)$'):
        f.register(artifact)
    assert store.read_head(f.root)['id'] == head


def test_stale_chain_requires_repair_without_mutating_old_revision(f):
    f.chain(complete=False); previous = current_node(_context(f.snapshot()), 'synthesize')[1]
    f.register(f.make('synthesize', previous_ref=previous, revision_reason='Correct synthesis'))
    result = api().prepare_hypothesis_review(f.snapshot())
    assert result['ready'] is False and 'hypothesize_stale' in result['reason_codes']
    assert result['node_refs']['hypothesize'] is None


def test_missing_prerequisites_projection_still_returns_prior_imported_issue_ids(tmp_path):
    from researchclaw.core.research_graph import migration
    from tests.codex_native.research_graph.test_migration import source_fixture, snapshot as files
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source); before = files(source)
    head = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    target_before = files(target)
    result = api().prepare_hypothesis_review(commands.read_policy_snapshot(target))
    assert result['ready'] is False and result['node_refs'] == dict(synthesize=None, hypothesize=None, review=None)
    assert result['unaccounted_issue_ids'] == sorted(head['state']['issues'])
    assert len(result['prior_issues']) == 6
    assert all(row['category'] == 'other' and row['owner_assignment_id'] is None for row in result['prior_issues'])
    assert 'prior_issue_unaccounted' in result['reason_codes']
    assert files(source) == before and files(target) == target_before


def test_explicit_import_materialization_enables_a05_checking_owner_without_rewriting_issue(tmp_path):
    from researchclaw.core.research_graph import migration
    from researchclaw.core.research_graph.gates import _status
    from tests.codex_native.research_graph.test_migration import source_fixture, snapshot as files
    from tests.codex_native.research_graph.test_m1_scope import Fixture as ScopeFixture, uid
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source); source_before = files(source)
    head = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    original = deepcopy(head['state']['issues'])
    f = ScopeFixture.__new__(ScopeFixture); f.root = target; f.head = head; f.project = head['state']['project_id']
    for identity in original:
        first = f.apply('m1.issue.materialize', {'issue_id': identity}, command_id=identity)
        assert f.head['state']['issues'] == original
        assert f.apply('m1.issue.materialize', {'issue_id': identity}, command_id=identity, expected_head=head['id']) == first
    f.register(f.node('scope')); f.council_prepare()
    # Explicit synthetic budget prerequisite: no measured execution/cost implied.
    budget = dict(id=uid(), project_id=f.project, returns_used=0, verification_runs_used=0, observed_cost=None, cost_status='unknown')
    f.head = store.commit_record(target, expected_head=f.head['id'], command_id=uid(), state=f.head['state'],
        event={**store._VERSION, 'type': 'synthetic_budget', 'payload': {}}, objects={budget['id']: store._canonical(budget)})
    budget_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=budget['id'], sha256=store._hash(store._canonical(budget)))
    issue = next(iter(original.values()))
    verification = {**f.envelope(), 'issue_ids': [issue['id']], 'method': 'logic_check', 'question': issue['question'],
        'input_refs': [f.binding], 'acceptance_rule': issue['resolution_condition'], 'owner_assignment_id': f.author['id'], 'budget_ref': budget_ref}
    f.apply('verification.prepare', {'verification': verification})
    ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=verification['id'], sha256=store._hash(store._canonical(verification)))
    event = {**f.envelope(), 'issue_id': issue['id'], 'from_status': 'open', 'to_status': 'checking',
        'actor_assignment_id': f.author['id'], 'owner_assignment_id': f.author['id'], 'rationale': 'Adopt explicit native recheck',
        'verification_refs': [ref], 'successor_ids': []}
    f.apply('issue.event', {'issue': None, 'event': event})
    result = api().prepare_hypothesis_review(f.snapshot())
    assert next(row for row in result['prior_issues'] if row['issue_id'] == issue['id'])['owner_assignment_id'] == f.author['id']
    assert _status(_context(f.snapshot()), issue)[0] == 'checking'
    outcome = {**f.envelope(), 'verification_id': verification['id'], 'output_refs': [f.binding],
        'outcome': 'supported', 'checked_scope': [issue['resolution_condition']], 'limitations': ['Synthetic policy evidence only']}
    f.apply('verification.result', {'verification_ref': ref, 'result': outcome})
    outcome_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=outcome['id'], sha256=store._hash(store._canonical(outcome)))
    resolver = f.reviewers[0]
    f.apply('issue.event', {'issue': None, 'event': {**f.envelope(resolver['actor_id']), 'issue_id': issue['id'],
        'from_status': 'checking', 'to_status': 'resolved', 'actor_assignment_id': resolver['id'],
        'rationale': 'Independent synthetic revalidation', 'verification_refs': [outcome_ref], 'successor_ids': []}})
    resolved_projection = api().prepare_hypothesis_review(f.snapshot())
    assert issue['id'] in resolved_projection['unaccounted_issue_ids']
    assert issue['id'] not in resolved_projection['unresolved_issue_ids']
    assert f.head['state']['issues'] == original and files(source) == source_before
    assert all(f.snapshot()['_issue_context']['objects'][store._hash(store._canonical(row))] == store._canonical(row) for row in original.values())
    before = f.head['id']
    with pytest.raises(ValueError, match='^m1_imported_issue_already_materialized$'):
        f.apply('m1.issue.materialize', {'issue_id': issue['id']})
    assert store.read_head(target)['id'] == before
    with pytest.raises(ValueError, match='^research_graph_head_conflict$'):
        f.apply('m1.issue.materialize', {'issue_id': issue['id']}, expected_head=head['id'])
    assert store.read_head(target)['id'] == before


def test_empirical_transfer_proposal_is_explicit_pending_obligation_not_resolution(f):
    f.chain('hypothesize', complete=False); f.council_prepare()
    issue = f.issue(); issue.update(category='empirical', blocking_scope=[]); f.publish(issue)
    artifact = f.make('review')
    artifact['content']['prior_issue_dispositions'] = [dict(issue_id=issue['id'], disposition='transfer_proposed',
        owner_assignment_id=f.author['id'], hypothesis_ids=['H1'], rationale='Requires a later empirical check', verification_refs=[])]
    artifact['content']['open_questions'] = [dict(issue_id=issue['id'], question=issue['question'],
        method='Prespecified group comparison', resolution_condition=issue['resolution_condition'],
        owner_assignment_id=f.author['id'], to_milestone='M2',
        budget_ref=next(iter(f.head['state']['verifications'].values()))['budget_ref'], limitations=['No experiment has run'])]
    f.register(artifact); result = api().prepare_hypothesis_review(f.snapshot())
    assert not result['ready'] and 'transfer_acceptance_required' in result['reason_codes']
    assert result['unresolved_issue_ids'] == [issue['id']] and not result['unaccounted_issue_ids']
    assert result['transfer_obligations'][0]['status'] == 'proposed'
    assert not f.head['state'].get('transfer_acceptances')


def test_changed_import_wrapper_cannot_be_materialized_as_authentic_source(tmp_path):
    from researchclaw.core.research_graph import migration
    from tests.codex_native.research_graph.test_migration import source_fixture
    from tests.codex_native.research_graph.test_m1_scope import uid
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    head = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    state = deepcopy(head['state']); identity = next(iter(state['issues']))
    state['issues'][identity]['question'] = 'Changed after import'
    head = store.commit_record(target, expected_head=head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_corruption', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='^m1_imported_issue_invalid$'):
        commands.apply_command(target, operation='m1.issue.materialize', payload={'issue_id': identity},
                               expected_head=head['id'], command_id=uid())
    assert store.read_head(target)['id'] == head['id']

def test_native_hypothesis_cannot_silently_mix_external_synthesis(f):
    from tests.codex_native.research_graph.test_external_evidence import imported, apply, review_payload
    from researchclaw.core.research_graph.views import build_view
    imported(f.root)
    e=build_view(f.root)['external_evidence'][0]['ref']
    apply(f.root,'external.review.record',review_payload(e))
    view=build_view(f.root);r=view['external_reviews'][0]['ref']
    question,qref=current_node(_context(f.snapshot()),'questions')
    p=dict(question_ref=qref,question_text=question['content']['questions'][0]['question'],review_refs=[r],
        claims=[dict(claim_id='c1',statement='External limited claim',evidence_ref=e,review_ref=r,
            basis_kind='atlas_answer',qa_excerpt='First answer',rationale='Synthetic test',
            intended_use='hypothesis review',limitations=[])],
        coverage=dict(covered='Test',missing='Empirical validation',decision_impact='Design only'),
        limitations=[],previous_ref=None,revision_reason=None,producer_id='author')
    apply(f.root,'m1.evidence_basis.register',p)
    basis=build_view(f.root)['m1_evidence_bases'][0]
    a=f.make('synthesize');a['input_refs']={'questions':qref,'evidence_basis':basis['ref']}
    a['content']['findings'][0]['evidence_refs']=[basis['claims'][0]['ref']]
    a['content']['rejected_alternatives']=[]
    f.head=store.read_head(f.root);f.register(a)
    hypothesis=f.make('hypothesize');hypothesis['content']['hypotheses'][0]['alternative_ids']=[]
    with pytest.raises(ValueError,match='m1_review_route_mismatch'):f.register(hypothesis)
