"""B07 synthetic native publication/acceptance, with one cached reviewed chain."""
from copy import deepcopy
import importlib
import shutil
from uuid import UUID, uuid5

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.gates import assess_gate
from researchclaw.core.research_graph.m1_nodes import _context, current_node
from tests.codex_native.research_graph.test_m1_review import (
    Fixture as ReviewFixture, extracted_baseline, collected_baseline, native_baseline)
from tests.codex_native.research_graph.test_m1_evidence import load
from tests.codex_native.research_graph.test_m1_scope import uid


def api():
    return importlib.import_module('researchclaw.core.research_graph.handoffs')


def accounting():
    return importlib.import_module('researchclaw.core.research_graph.work_accounting')


class Fixture(ReviewFixture):
    def account(self):
        for source in accounting().work_sources(self.snapshot()):
            if not source['recorded']:
                self.apply('m1.work.record', dict(record_id=uid(), source_kind=source['source_kind'], source_ref=source['source_ref']))
        self.apply('work_ledger.refresh', {'ledger_id': uid()})

    def issue_package(self, **extra):
        publication = self.envelope()
        self.apply('m1.handoff.issue', dict(publication=publication,
            review_ref=current_node(_context(self.snapshot()), 'review')[1], **extra))
        self.package_id = publication['id']
        return api().handoff_status(self.snapshot(), handoff_id=self.package_id)

    def receiver(self, actor='receiver'):
        status = api().handoff_status(self.snapshot(), handoff_id=self.package_id)
        self.receiver_assignment = dict(id=status['receiver_assignment_id'], project_id=self.project,
            actor_id=actor, role='owner', milestone='M2', active=True)
        self.apply('m1.handoff.receiver.assign', dict(handoff_ref=status['handoff_ref'], assignment=self.receiver_assignment))

    def accept(self, refs=()):
        status = api().handoff_status(self.snapshot(), handoff_id=self.package_id)
        return self.apply('m1.handoff.accept', dict(acceptance=self.envelope(self.receiver_assignment['actor_id']),
            handoff_ref=status['handoff_ref'], receiver_assignment_id=self.receiver_assignment['id'],
            verification_refs=list(refs), limitations=['Receiving the declared questions; no experiments run']))


def reload(root):
    f = load(root, 'review'); f.__class__ = Fixture
    return f


@pytest.fixture(scope='module')
def reviewed_baseline(extracted_baseline, tmp_path_factory):
    root = tmp_path_factory.mktemp('b07-reviewed') / 'project'; shutil.copytree(extracted_baseline, root)
    f = load(root, 'extract'); f.__class__ = Fixture; f.chain()
    return root


@pytest.fixture(scope='module')
def accounted_baseline(reviewed_baseline, tmp_path_factory):
    root = tmp_path_factory.mktemp('b07-accounted') / 'project'; shutil.copytree(reviewed_baseline, root)
    f = reload(root); f.account()
    return root


@pytest.fixture
def f(accounted_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(accounted_baseline, root)
    return reload(root)


def test_native_issuefree_publication_acceptance_and_gate_do_not_initialize_m2(f):
    old = f.snapshot()['_issue_context']['objects'].copy(); head = f.head['id']
    issued = f.issue_package()
    assert issued['status'] == 'issued_awaiting_acceptance' and issued['gate_ready'] is False
    assert issued['handoff_ref']['head_id'] != head and issued['manifest']['source_groups']['origin_group_count'] == 1
    assert issued['manifest']['rejected_alternatives'] and issued['manifest']['limitations']
    assert 'handoff_acceptance_required' in issued['reason_codes']
    f.receiver(); f.accept(); accepted = api().handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert accepted['status'] == 'accepted' and accepted['gate_ready'] is True
    assert assess_gate(f.snapshot(), milestone='M1', gate_id=accepted['gate_id'])['ready'] is True
    assert not f.head['state'].get('experiments') and not f.head['state'].get('m2_node_heads')
    objects = f.snapshot()['_issue_context']['objects']
    assert all(objects[digest] == data for digest, data in old.items())
    # A later call must inspect the new current Issue, not reuse prior ready.
    artifact = current_node(_context(f.snapshot()), 'review')[0]
    council = next(c for c in f.head['state']['councils'].values() if c['attempt'] == artifact['attempt'])
    f.author = f.head['state']['assignments'][council['author_assignment_ids'][0]]
    f.binding = current_node(_context(f.snapshot()), 'review')[1]
    issue = f.issue(producer='author'); issue.update(category='integrity', blocking_scope=[dict(kind='handoff', milestone='M1', target_id='M2')])
    f.publish(issue)
    blocked = api().handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert blocked['status'] == 'accepted' and not blocked['gate_ready']
    assert 'handoff_issue_unresolved' in blocked['reason_codes']
    assert not assess_gate(f.snapshot(), milestone='M1', gate_id=blocked['gate_id'])['ready']


def test_missing_backed_native_work_accounting_blocks_publication(reviewed_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(reviewed_baseline, root); f = reload(root); head = f.head['id']
    with pytest.raises(ValueError, match='^work_record_required$'):
        f.issue_package()
    assert store.read_head(root)['id'] == head


def test_changed_corpus_binding_is_stale_handoff_and_acceptance_preserves_head(f):
    f.issue_package(); f.receiver()
    inputs = _context(f.snapshot()); screen, ref = current_node(inputs, 'screen')
    content = deepcopy(screen['content']); content['candidates'][0]['title'] += ' corrected metadata'
    f.register(f.node('screen', input_refs=screen['input_refs'], previous_ref=ref,
                     revision_reason='New source information', content=content))
    before = f.head['id']
    status = api().handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert not status['gate_ready'] and 'stale_handoff' in status['reason_codes']
    with pytest.raises(ValueError, match='^stale_handoff$'):
        f.accept()
    assert store.read_head(f.root)['id'] == before


def test_receiver_cannot_be_the_m1_author(f):
    f.issue_package(); before = f.head['id']
    with pytest.raises(ValueError, match='^handoff_receiver_invalid$'):
        f.receiver(actor='author')
    assert store.read_head(f.root)['id'] == before


def test_native_work_units_are_once_only_and_unknown_cost_is_preserved(f):
    counters = (f.head['state']['returns_used'], f.head['state']['verification_runs_used'])
    assert counters == (0, 2)
    sources = accounting().work_sources(f.snapshot()); assert all(source['recorded'] for source in sources)
    before = f.head['id']
    with pytest.raises(ValueError, match='^work_source_already_recorded$'):
        f.apply('m1.work.record', dict(record_id=uid(), source_kind=sources[0]['source_kind'], source_ref=sources[0]['source_ref']))
    assert store.read_head(f.root)['id'] == before
    f.apply('work_ledger.refresh', {'ledger_id': uid()})
    assert (f.head['state']['returns_used'], f.head['state']['verification_runs_used']) == counters
    assert f.head['state']['observed_cost'] is None and f.head['state']['cost_status'] == 'unknown'
    record = next(iter(f.head['state']['work_records'].values()))
    work = {**record['work'], 'id': uid(), 'event_id': uid()}
    result = importlib.import_module('researchclaw.core.research_graph.budgets').assess_next_work(f.snapshot(),
        dict(work=work, resource_request=record['resource_request'], correction_ref=None,
             correction_approval_ref=None, semantic_status='literal_only', resume_ref=None))
    assert not result['ready'] and 'repeated_work' in result['reason_codes']


def test_empirical_issue_requires_exact_acceptance_then_native_owner_transfer(f):
    # One true end-to-end transfer uses the cached authentic reviewed predecessor.
    current = current_node(_context(f.snapshot()), 'review')[0]
    council = next(c for c in f.head['state']['councils'].values() if c['attempt'] == current['attempt'])
    f.author = f.head['state']['assignments'][council['author_assignment_ids'][0]]
    f.reviewers = [f.head['state']['assignments'][identity] for identity in council['required_roles'].values()]
    f.binding = current_node(_context(f.snapshot()), 'review')[1]
    issue = f.issue(producer='author'); issue['category'] = 'empirical'
    issue['target_refs'] = [current_node(_context(f.snapshot()), 'hypothesize')[1]]
    f.publish(issue)
    old_review = f.binding; old_issue_bytes = store._canonical(issue); m1_owner = deepcopy(f.author)
    revision = f.make('hypothesize', previous_ref=issue['target_refs'][0], revision_reason='Clarify the empirical prediction')
    revision['content']['hypotheses'][0]['prediction'] += ' under the frozen population comparison'
    f.register(revision); f.council_prepare(); f.complete()
    artifact = f.make('review', previous_ref=old_review, revision_reason='Carry empirical question to M2')
    artifact['content']['prior_issue_dispositions'] = [dict(issue_id=issue['id'], disposition='transfer_proposed',
        owner_assignment_id=m1_owner['id'], hypothesis_ids=['H1'], rationale='Needs empirical verification', verification_refs=[])]
    artifact['content']['open_questions'] = [dict(issue_id=issue['id'], question=issue['question'], method='Prespecified comparison',
        resolution_condition=issue['resolution_condition'], owner_assignment_id=m1_owner['id'], to_milestone='M2',
        budget_ref=next(iter(f.head['state']['verifications'].values()))['budget_ref'], limitations=['Untested prediction'])]
    f.register(artifact); f.council_prepare()
    from researchclaw.core.research_graph.councils import reviewer_packet
    packet = reviewer_packet(f.snapshot(), f.reviewers[0]['id'])
    assert packet['shared_issues'][0]['issue'] == issue
    assert issue['target_refs'][0] not in packet['allowed_evidence_refs']
    f.complete(); f.account()
    issued = f.issue_package(); frozen_review = store._canonical(f.head['state']['m1_node_revisions'][artifact['id']])
    assert issued['status'] == 'issued_awaiting_acceptance' and not issued['gate_ready']
    f.receiver(); before = f.head['id']
    with pytest.raises(ValueError, match='^handoff_verification_invalid$'):
        f.accept()
    assert store.read_head(f.root)['id'] == before
    proposal = issued['transfer_proposals'][0]
    verification = {**f.envelope('receiver'), 'id': proposal['verification_id'], 'issue_ids': [issue['id']],
        'method': 'experiment', 'question': issue['question'], 'input_refs': issued['verification_input_refs'],
        'acceptance_rule': issue['resolution_condition'], 'owner_assignment_id': f.receiver_assignment['id'],
        'budget_ref': artifact['content']['open_questions'][0]['budget_ref']}
    f.apply('verification.prepare', {'verification': verification})
    ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=verification['id'], sha256=store._hash(store._canonical(verification)))
    f.account(); f.accept([ref]); accepted = api().handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert accepted['status'] == 'accepted' and not accepted['gate_ready']
    assert 'native_transfer_required' in accepted['reason_codes']
    acceptance_id = accepted['transfer_acceptance_ids'][issue['id']]
    event = {**f.envelope(m1_owner['actor_id']), 'issue_id': issue['id'], 'from_status': 'open', 'to_status': 'transferred',
        'actor_assignment_id': m1_owner['id'], 'rationale': 'Transfer after explicit receiver acceptance', 'verification_refs': [],
        'successor_ids': [], 'to_milestone': 'M2', 'owner_assignment_id': f.receiver_assignment['id'],
        'verification_id': verification['id'], 'acceptance_event_id': acceptance_id}
    wrong_root = f.root.parent / 'wrong-owner'; shutil.copytree(f.root, wrong_root)
    wrong = reload(wrong_root)
    other = f.reviewers[0]
    wrong.apply('issue.event', {'issue': None, 'event': {**event, 'actor_assignment_id': other['id'], 'producer_id': other['actor_id']}})
    refused = api().handoff_status(wrong.snapshot(), handoff_id=f.package_id)
    assert not refused['gate_ready'] and 'handoff_transfer_owner_invalid' in refused['reason_codes']
    f.apply('issue.event', {'issue': None, 'event': event})
    final = api().handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert final['status'] == 'accepted' and final['gate_ready'] is True
    assert assess_gate(f.snapshot(), milestone='M1', gate_id=final['gate_id'])['ready'] is True
    assert f.head['state']['issues'][issue['id']] == issue
    assert f.snapshot()['_issue_context']['objects'][store._hash(old_issue_bytes)] == old_issue_bytes
    assert f.snapshot()['_issue_context']['objects'][store._hash(frozen_review)] == frozen_review
    assert not any(result['verification_id'] == verification['id'] for result in f.head['state'].get('verification_results', {}).values())


def test_closed_publication_payload_rejects_caller_ready_before_any_mutation(tmp_path):
    head = commands.init_project(tmp_path, topic='Closed handoff', content_origin='synthetic')
    with pytest.raises(ValueError, match='^handoff_payload_invalid$'):
        commands.apply_command(tmp_path, operation='m1.handoff.issue', payload={'ready': True},
                               expected_head=head['id'], command_id=uid())
    assert store.read_head(tmp_path)['id'] == head['id']


def test_materialized_imported_issue_context_does_not_grant_foreign_target_access(tmp_path):
    from researchclaw.core.m1 import store as legacy
    from researchclaw.core.research_graph import migration
    from researchclaw.core.research_graph.councils import reviewer_packet
    from tests.codex_native.research_graph.test_migration import source_fixture, snapshot as files
    from tests.codex_native.research_graph.test_m1_scope import Fixture as ScopeFixture
    source, target = tmp_path / 'source', tmp_path / 'target'
    selected = source_fixture(source)
    data = legacy._canonical({'hypotheses': [{'id': 'H1', 'revision': 1, 'statement': 'Archived prediction'}]})
    ref = dict(id='old-hypothesis', sha256=legacy._hash(data), size=len(data), logical_path='hypotheses/hypotheses.json')
    state = deepcopy(selected['state']); state['artifacts'] = [ref]; state['sessions']['r1']['input_refs'] = [ref]
    state['sessions']['r1']['disclosed_initials'][0]['open_issues'][0]['target_refs'] = [dict(id='H1', revision=1)]
    selected = legacy.commit_record(source, expected_head=selected['id'], command_id='target', state=state,
        event={**legacy._VERSION, 'type': 'fixture', 'payload': {}}, objects={'old.json': data})
    before = files(source)
    head = migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    f = ScopeFixture.__new__(ScopeFixture); f.root = target; f.head = head; f.project = head['state']['project_id']
    for identity_ in head['state']['issues']:
        f.apply('m1.issue.materialize', {'issue_id': identity_})
    f.register(f.node('scope')); payload = f.council_payload(); payload['council']['issue_ids'] = sorted(head['state']['issues'])
    f.apply('council.prepare', payload); f.submitted = dict(initial=[], response=[], final=[])
    packet = reviewer_packet(f.snapshot(), f.reviewers[0]['id'])
    historical = next(issue for issue in head['state']['issues'].values() if issue['target_refs'])
    foreign_ref = historical['target_refs'][0]
    assert next(row['issue'] for row in packet['shared_issues'] if row['issue']['id'] == historical['id']) == historical
    assert foreign_ref not in packet['allowed_evidence_refs']
    before_head = f.head['id']
    with pytest.raises(ValueError, match='^dependency_reference_invalid$'):
        f.submit(0, 'initial', evidence_refs=[foreign_ref])
    assert store.read_head(target)['id'] == before_head and files(source) == before


@pytest.mark.parametrize('completed', [False, True])
def test_abandoned_wrong_author_council_allows_native_repair_accounting(tmp_path, completed):
    from tests.codex_native.research_graph.test_m1_scope import Fixture as ScopeFixture
    f = ScopeFixture(tmp_path); f.register(); prior = f.check()['node_ref']
    f.council_prepare(author='wrong-author')
    if completed:
        f.complete()
    else:
        f.submit(0, 'initial')
    abandoned = deepcopy(f.council)
    old_objects = f.snapshot()['_issue_context']['objects'].copy()
    f.register(f.node(previous_ref=prior, revision_reason='Repair the mismatched author setup'))
    f.council_prepare(); f.complete()
    assert f.check()['ready'] is True
    before = f.head['id']; snapshot = f.snapshot()
    sources = accounting().work_sources(snapshot)
    assert store.read_head(tmp_path)['id'] == before
    assert [source['source_ref']['artifact_id'] for source in sources] == [f.council['id']]
    unbacked = deepcopy(snapshot)
    del unbacked['_issue_context']['objects'][store._hash(store._canonical(abandoned))]
    with pytest.raises(ValueError, match='^(issue_reference_invalid|issue_prerequisite_unbacked)$'):
        accounting().work_sources(unbacked)
    forged = deepcopy(snapshot)
    first = next(record for _, record in forged['_issue_context']['history']
                 if abandoned['id'] in record['state'].get('councils', {}))
    first['events'][-1]['type'] = 'not_native_council_preparation'
    with pytest.raises(ValueError, match='^m1_native_record_invalid$'):
        accounting().work_sources(forged)
    assert store.read_head(tmp_path)['id'] == before
    for source in sources:
        f.apply('m1.work.record', dict(record_id=uid(), source_kind=source['source_kind'], source_ref=source['source_ref']))
    f.apply('work_ledger.refresh', {'ledger_id': uid()})
    assert accounting().accounting_status(f.snapshot())['ready'] is True
    assert f.head['state']['returns_used'] == 1 and f.head['state']['verification_runs_used'] == 0
    assert f.head['state']['observed_cost'] is None and f.head['state']['cost_status'] == 'unknown'
    assert f.head['state']['councils'][abandoned['id']] == abandoned
    assert all(f.snapshot()['_issue_context']['objects'][key] == value for key, value in old_objects.items())
    # Exclusion is not permission to materialize invalid historical work.
    ref = accounting()._record_ref(accounting()._context(f.snapshot()), 'councils', abandoned)
    head = f.head['id']
    with pytest.raises(ValueError, match='^work_source_ineligible$'):
        f.apply('m1.work.record', dict(record_id=uid(), source_kind='council', source_ref=ref))
    assert store.read_head(tmp_path)['id'] == head


def test_active_completed_wrong_author_council_still_rejects_work(tmp_path):
    from tests.codex_native.research_graph.test_m1_scope import Fixture as ScopeFixture
    f = ScopeFixture(tmp_path); f.register(); f.council_prepare(author='wrong-author'); f.complete()
    head = f.head['id']; snapshot = f.snapshot()
    with pytest.raises(ValueError, match='^m1_council_author_mismatch$'):
        accounting().work_sources(snapshot)
    ref = accounting()._record_ref(accounting()._context(snapshot), 'councils', f.council)
    with pytest.raises(ValueError, match='^m1_council_author_mismatch$'):
        f.apply('m1.work.record', dict(record_id=uid(), source_kind='council', source_ref=ref))
    with pytest.raises(ValueError, match='^m1_council_author_mismatch$'):
        f.apply('work_ledger.refresh', {'ledger_id': uid()})
    assert store.read_head(tmp_path)['id'] == head
