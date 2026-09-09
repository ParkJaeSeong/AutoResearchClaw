"""B05 native synthetic captures/checks; cached approved-screen prerequisites."""
from copy import deepcopy
import importlib
import json
import shutil

import pytest

from researchclaw.core.research_graph import commands, store
from tests.codex_native.research_graph.test_m1_search import Fixture as SearchFixture, native_baseline
from tests.codex_native.research_graph.test_m1_scope import uid


def api():
    return importlib.import_module('researchclaw.core.research_graph.m1_evidence')


class Fixture(SearchFixture):
    def check(self, node=None):
        node = node or self.artifact['node']
        if node in ('collect', 'extract'):
            return api().prepare_evidence_check(self.snapshot(), node_id=node)
        return super().check(node)

    def collect(self, sources=None, previous=None):
        corpus = importlib.import_module('researchclaw.core.research_graph.m1_search').current_corpus(self.snapshot())
        rows = sources or [dict(source_id=s['source_id'], access_status='abstract', access_url=f"https://example.org/{s['source_id']}",
            accessed_at='2026-09-09T00:00:00Z', raw_text='Value: 42.', origin_group_id='dataset-A',
            origin_description='Same declared dataset', limitations=['Abstract access only']) for s in corpus['kept_sources']]
        artifact = super().node('collect', input_refs={'screen': corpus['corpus_ref']}, content={'sources': rows, 'limitations': []},
            previous_ref=previous, revision_reason='Update capture' if previous else None)
        self.register(artifact)

    def extract(self, value='42', **changes):
        projection = api().current_evidence(self.snapshot())
        claims = [dict(claim_id=f'claim-{source}', source_id=source, source_ref=refs['raw_ref'], locator='Recorded abstract value',
            span_start=7, span_end=9, extracted_text=value, access_level='abstract', interpretation='A declared numeric result',
            limitations=['Abstract access only']) for source, refs in projection['collected_source_refs'].items() if refs['raw_ref']]
        artifact = super().node('extract', input_refs={'screen': projection['corpus_ref'], 'collect': projection['collect_ref']},
            content={'claims': claims, 'limitations': []}, **changes)
        self.register(artifact)

    def setup(self):
        self.checker = dict(id=uid(), project_id=self.project, actor_id=f"checker-{self.artifact['node']}", role='owner', milestone='M1', active=True)
        self.resolver = dict(id=uid(), project_id=self.project, actor_id=f"resolver-{self.artifact['node']}", role='resolver', milestone='M1', active=True)
        self.apply('m1.evidence.assign', dict(setup_id=uid(), node_ref=self.check()['node_ref'],
            checker_assignment=self.checker, resolver_assignment=self.resolver))
        for _ in range(4):
            plans = self.check()['command_plans']
            if not plans:
                break
            self.apply(plans[0]['operation'], plans[0]['payload'])
        return self.check()

    def observe(self, **changes):
        check = self.check(); projection = api().current_evidence(self.snapshot())
        comparisons = []
        if self.artifact['node'] == 'collect':
            for source in self.artifact['content']['sources']:
                if source['raw_text'] is not None:
                    comparisons.append(dict(item_id=source['source_id'], source_ref=projection['collected_source_refs'][source['source_id']]['raw_ref'],
                        locator='Supplied capture', span_start=0, span_end=len(source['raw_text']), access_level=source['access_status'],
                        observed_text=source['raw_text'], interpretation='Inspected the supplied capture'))
        else:
            objects = self.snapshot()['_issue_context']['objects']
            for claim in self.artifact['content']['claims']:
                text = objects[claim['source_ref']['sha256']].decode()
                comparisons.append(dict(item_id=claim['claim_id'], source_ref=claim['source_ref'], locator=claim['locator'],
                    span_start=claim['span_start'], span_end=claim['span_end'], access_level=claim['access_level'],
                    observed_text=text[claim['span_start']:claim['span_end']], interpretation='Literal source comparison'))
        observation = {**self.envelope(self.checker['actor_id']), 'verification_ref': check['verification_ref'],
            'node_ref': check['node_ref'], 'checker_assignment_id': self.checker['id'], 'comparisons': comparisons,
            'limitations': ['Supplied captures only; not authenticated'], **changes}
        result = self.apply('m1.evidence.observe', {'observation': observation})
        return dict(project_id=self.project, head_id=result['id'], artifact_id=observation['id'],
                    sha256=store._hash(store._canonical(observation)))

    def result_and_resolution(self, output, outcome='supported', resolve=True):
        check = self.check(); verification = self.head['state']['verifications'][check['verification_ref']['artifact_id']]
        result = {**self.envelope(self.checker['actor_id']), 'verification_id': verification['id'], 'output_refs': [output],
            'outcome': outcome, 'checked_scope': [verification['acceptance_rule']], 'limitations': ['Supplied capture limitation']}
        self.apply('verification.result', {'verification_ref': check['verification_ref'], 'result': result})
        result_ref = dict(project_id=self.project, head_id=self.head['id'], artifact_id=result['id'], sha256=store._hash(store._canonical(result)))
        if resolve:
            event = {**self.envelope(self.resolver['actor_id']), 'issue_id': verification['issue_ids'][0], 'from_status': 'checking',
                'to_status': 'resolved', 'actor_assignment_id': self.resolver['id'], 'rationale': 'Independently accept fixed source check',
                'verification_refs': [result_ref], 'successor_ids': []}
            self.apply('issue.event', {'issue': None, 'event': event})


def load(root, node):
    f = Fixture.__new__(Fixture); f.root = root; f.head = store.read_head(root); f.project = f.head['state']['project_id']
    artifact = deepcopy(f.head['state']['m1_node_revisions'][f.head['state']['m1_node_heads'][node]])
    prior = artifact.pop('previous_ref_key'); artifact['previous_ref'] = json.loads(prior) if prior else None; f.artifact = artifact
    return f


@pytest.fixture(scope='module')
def collected_baseline(native_baseline, tmp_path_factory):
    root = tmp_path_factory.mktemp('b05-collected') / 'project'; shutil.copytree(native_baseline, root)
    f = load(root, 'screen'); f.bind(f.decide()); f.collect(); f.setup(); output = f.observe(); f.result_and_resolution(output)
    assert f.check()['ready'] is True
    return root


@pytest.fixture
def f(collected_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(collected_baseline, root)
    return load(root, 'collect')


def test_native_source_capture_index_and_independent_a05_checks_connect_complete_evidence(f):
    captured = api().current_evidence(f.snapshot())['collected_source_refs']
    before = {row['raw_ref']['sha256']: f.snapshot()['_issue_context']['objects'][row['raw_ref']['sha256']]
              for row in captured.values()}
    f.extract(); f.setup(); output = f.observe(); f.result_and_resolution(output)
    projection = api().current_evidence(f.snapshot())
    assert projection['ready'] is True and projection['reason_codes'] == []
    assert all(f.snapshot()['_issue_context']['objects'][digest] == data for digest, data in before.items())
    assert store.read_head(f.root)['id'] == f.head['id']
    assert projection['kept_source_ids'] == ['paper-1', 'paper-2']
    assert len(projection['extraction_refs']) == 2
    assert projection['source_groups']['source_count'] == 2 and projection['source_groups']['origin_group_count'] == 1
    assert projection['limitations']
    assert f.head['state']['m1_node_revisions'][f.artifact['id']]['input_refs']['screen'] == projection['corpus_ref']


def test_mismatch_is_preserved_as_separate_issue_plan_even_with_supported_result(f):
    f.extract(value='99'); f.setup(); output = f.observe(); check = f.check()
    assert 'source_mismatch' in check['reason_codes'] and check['mismatch_issue_plans']
    planned = check['check_issue_id']
    assert all(plan['payload']['issue']['id'] != planned for plan in check['mismatch_issue_plans'])
    assert all(plan['payload']['issue']['category'] == 'source' for plan in check['mismatch_issue_plans'])
    assert all(plan['payload']['issue']['id'] not in f.head['state']['issues'] for plan in check['mismatch_issue_plans'])
    f.result_and_resolution(output)
    assert api().current_evidence(f.snapshot())['ready'] is False
    assert 'source_mismatch' in f.check()['reason_codes']


def test_abstract_capture_cannot_be_reported_as_full_text_check(f):
    f.extract(); f.setup(); check = f.check(); claim = f.artifact['content']['claims'][0]
    comparison = dict(item_id=claim['claim_id'], source_ref=claim['source_ref'], locator=claim['locator'],
        span_start=7, span_end=9, access_level='full_text', observed_text='42', interpretation='Incorrect access claim')
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_evidence_access_invalid$'):
        f.observe(comparisons=[comparison])
    assert store.read_head(f.root)['id'] == head


def test_extractor_cannot_produce_checker_observation(f):
    f.extract(); f.setup(); head = f.head['id']
    with pytest.raises(ValueError, match='^m1_evidence_actor_invalid$'):
        f.observe(producer_id='author')
    assert store.read_head(f.root)['id'] == head


def test_generic_supported_result_and_resolution_without_native_observation_never_ready(f):
    f.extract(); f.setup(); f.result_and_resolution(f.check()['node_ref'])
    assert 'source_observation_required' in f.check()['reason_codes']
    assert api().current_evidence(f.snapshot())['ready'] is False


def test_inconclusive_native_result_remains_explicit_gap(f):
    f.extract(); f.setup(); output = f.observe(); f.result_and_resolution(output, outcome='inconclusive', resolve=False)
    assert 'source_check_inconclusive' in f.check()['reason_codes']
    assert api().current_evidence(f.snapshot())['ready'] is False


@pytest.mark.parametrize('fault', ['outside_source', 'wrong_source_ref', 'missing_coverage'])
def test_invalid_extraction_source_binding_refused_and_head_preserved(f, fault):
    projection = api().current_evidence(f.snapshot()); source = projection['collected_source_refs']['paper-1']
    claim = dict(claim_id='claim-1', source_id='paper-1', source_ref=source['raw_ref'], locator='Value', span_start=7, span_end=9,
        extracted_text='42', access_level='abstract', interpretation='Declared value', limitations=['Abstract only'])
    if fault == 'outside_source': claim['source_id'] = 'outside'
    if fault == 'wrong_source_ref': claim['source_ref'] = source['metadata_ref']
    head = f.head['id']
    artifact = SearchFixture.node(f, 'extract', input_refs={'screen': projection['corpus_ref'], 'collect': projection['collect_ref']},
        content={'claims': [claim], 'limitations': []})
    with pytest.raises(ValueError, match='^m1_evidence_(source|coverage)_invalid$'):
        f.register(artifact)
    assert store.read_head(f.root)['id'] == head


def test_extract_requires_current_explicit_corpus_authority(f):
    screen = api().current_evidence(f.snapshot())['corpus_ref']; f.decide('reject', corpus_ref=screen); head = f.head['id']
    with pytest.raises(ValueError, match='^m1_corpus_approval_required$'):
        f.extract()
    assert store.read_head(f.root)['id'] == head


def test_unavailable_kept_source_has_no_fabricated_raw_ref_or_observation(f):
    prior = f.check()['node_ref']; sources = deepcopy(f.artifact['content']['sources'])
    sources[1].update(access_status='unavailable', raw_text=None, origin_group_id='unknown', origin_description=None,
                      limitations=['Kept original could not be accessed'])
    f.collect(sources=sources, previous=prior); f.setup(); output = f.observe()
    f.result_and_resolution(output, outcome='inconclusive', resolve=False)
    projection = api().current_evidence(f.snapshot())
    assert projection['collected_source_refs']['paper-2']['raw_ref'] is None
    assert projection['source_groups']['unknown_refs']
    assert projection['ready'] is False and projection['limitations']


def test_unpublished_mismatch_cannot_be_erased_by_revision(f):
    f.extract(value='99'); f.setup(); f.observe()
    previous = f.check()['node_ref']; head = f.head['id']
    with pytest.raises(ValueError, match='^m1_issue_publication_required$'):
        f.extract(previous_ref=previous, revision_reason='Repair mismatched claim')
    assert store.read_head(f.root)['id'] == head
    for plan in f.check()['mismatch_issue_plans']:
        f.apply(plan['operation'], plan['payload'])
    f.extract(previous_ref=previous, revision_reason='Repair after publishing source issue')
    assert 'blocking_issue_unresolved' in f.check()['reason_codes']


def test_extract_revision_repairs_obsolete_collect_inputs(f):
    collect = deepcopy(f.artifact); collect_ref = f.check()['node_ref']
    f.extract(); previous = f.check()['node_ref']; old_extract = deepcopy(f.artifact)
    rows = deepcopy(collect['content']['sources'])
    for row in rows:
        row['raw_text'] += ' Additional supplied text.'
    f.collect(sources=rows, previous=collect_ref)
    new_collect = f.check()['node_ref']; capture_head = f.head['id']
    f.setup(); output = f.observe(); f.result_and_resolution(output)
    claims = deepcopy(old_extract['content']['claims'])
    for claim, source in zip(claims, rows):
        claim['source_ref'].update(head_id=capture_head, sha256=store._hash(source['raw_text'].encode()))
    artifact = SearchFixture.node(f, 'extract', previous_ref=previous, revision_reason='Use revised captures',
        input_refs={'screen': old_extract['input_refs']['screen'], 'collect': new_collect},
        content={'claims': claims, 'limitations': []})
    f.register(artifact)
    assert f.check()['node_ref']['sha256'] != previous['sha256']


def test_prior_inconclusive_check_resolves_by_explicit_a05_recheck_of_replacement(f):
    f.extract(); f.setup(); output = f.observe(); f.result_and_resolution(output, outcome='inconclusive', resolve=False)
    prior_check = f.check(); old_checker, old_resolver = deepcopy(f.checker), deepcopy(f.resolver)
    old_issue = deepcopy(f.head['state']['issues'][prior_check['check_issue_id']])
    old_result = next(r for r in f.head['state']['verification_results'].values()
                      if r['verification_id'] == prior_check['verification_ref']['artifact_id'])
    old_bytes = {store._hash(store._canonical(r)): store._canonical(r) for r in (old_issue, old_result)}
    f.extract(previous_ref=prior_check['node_ref'], revision_reason='Repeat inconclusive source inspection')
    f.setup(); replacement_output = f.observe(); f.result_and_resolution(replacement_output)
    assert 'blocking_issue_unresolved' in f.check()['reason_codes']

    def transition(status, previous, refs=(), actor=None):
        actor = actor or old_checker
        event = {**f.envelope(actor['actor_id']), 'issue_id': old_issue['id'], 'from_status': previous,
            'to_status': status, 'actor_assignment_id': actor['id'], 'rationale': 'Explicit recheck against replacement evidence',
            'verification_refs': list(refs), 'successor_ids': []}
        f.apply('issue.event', {'issue': None, 'event': event})

    transition('open', 'checking')
    current_check = f.check()
    prepared = f.head['state']['verifications'][current_check['verification_ref']['artifact_id']]
    verification = {**prepared, **f.envelope(old_checker['actor_id']), 'issue_ids': [old_issue['id']],
                    'owner_assignment_id': old_checker['id'], 'acceptance_rule': old_issue['resolution_condition']}
    f.apply('verification.prepare', {'verification': verification})
    verification_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=verification['id'],
                            sha256=store._hash(store._canonical(verification)))
    transition('checking', 'open', [verification_ref])
    result = {**f.envelope(old_checker['actor_id']), 'verification_id': verification['id'],
        'output_refs': [replacement_output], 'outcome': 'supported',
        'checked_scope': [old_issue['resolution_condition']], 'limitations': ['Supplied captures only']}
    f.apply('verification.result', {'verification_ref': verification_ref, 'result': result})
    result_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=result['id'], sha256=store._hash(store._canonical(result)))
    transition('resolved', 'checking', [result_ref], old_resolver)
    assert api().current_evidence(f.snapshot())['ready'] is True
    assert f.head['state']['issues'][old_issue['id']] == old_issue
    assert all(f.snapshot()['_issue_context']['objects'][digest] == data for digest, data in old_bytes.items())


@pytest.mark.parametrize('fault', ['nonmapping', 'missing_fields', 'list_artifact', 'null_artifact', 'invalid_head', 'extra_field'])
def test_assignment_malformed_node_ref_rejected_and_head_preserved(tmp_path, fault):
    root = tmp_path / 'project'
    head = commands.init_project(root, topic='Malformed assignment reference', content_origin='synthetic')
    ref = dict(project_id=head['state']['project_id'], head_id=head['id'], artifact_id='m1/nodes/collect', sha256='0' * 64)
    if fault == 'nonmapping': ref = []
    if fault == 'missing_fields': ref = {'artifact_id': 'm1/nodes/collect'}
    if fault == 'list_artifact': ref['artifact_id'] = []
    if fault == 'null_artifact': ref['artifact_id'] = None
    if fault == 'invalid_head': ref['head_id'] = []
    if fault == 'extra_field': ref['unexpected'] = True
    with pytest.raises(ValueError, match='^m1_evidence_setup_invalid$'):
        commands.apply_command(root, operation='m1.evidence.assign', expected_head=head['id'], command_id=uid(),
            payload=dict(setup_id=uid(), node_ref=ref, checker_assignment={}, resolver_assignment={}))
    assert store.read_head(root)['id'] == head['id']
