"""Invented data exercise real-labelled contracts, never actual experiment readiness."""
from copy import deepcopy
from types import MethodType
import pytest
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.handoffs import handoff_status
from researchclaw.core.research_graph.gates import assess_gate
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_handoffs import Fixture as HandoffFixture
from tests.codex_native.research_graph.test_m1_preparation_verification import prepared_real, verify
from tests.codex_native.research_graph.test_external_evidence import apply, imported, qa


@pytest.fixture
def package(prepared_real):
    f, p = prepared_real
    for name in ('account', 'issue_package', 'receiver', 'accept'):
        setattr(f, name, MethodType(getattr(HandoffFixture, name), f))
    f.account()
    return f, p


def test_external_publication_acceptance_and_history(package):
    f, p = package
    issued = f.issue_package()
    manifest = issued['manifest']
    assert manifest['route'] == 'external'
    assert 'Unverified' in manifest['limitations']
    assert set(manifest['node_refs']) == {'scope','questions','synthesize','hypothesize','review'}
    assert 'corpus_ref' not in manifest and 'source_groups' not in manifest
    assert not issued['gate_ready'] and 'handoff_acceptance_required' in issued['reason_codes']
    f.receiver(); f.accept()
    accepted = handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert accepted['gate_ready']
    view = build_view(f.root)
    assert len(view['m1_preparation_verifications']) == 7
    assert len(view['m1_preparation_evidence']) == 7
    assert all(row['source_ref']['sha256'] == row['record']['sha256'] for row in view['m1_preparation_evidence'])
    assert assess_gate(f.snapshot(), milestone='M1', gate_id=accepted['gate_id'])['ready']
    head = f.head['id']
    assert not f.head['state'].get('approvals') and not f.head['state'].get('experiments')
    assert not {'collect','extract','screen','search'} & set(f.head['state']['m1_node_heads'])
    imported(f.root, qa('Updated QA'))
    assert not handoff_status(f.snapshot(), handoff_id=f.package_id)['gate_ready']
    old = build_view(f.root, head_id=head)
    assert old['handoffs'][0]['assessment']['gate_ready']


@pytest.mark.parametrize('change', ['qa', 'preparation', 'rejected_check'])
def test_new_inputs_block_acceptance_without_rewriting_issued_package(package, change):
    f, p = package
    issued = f.issue_package(); f.receiver()
    if change == 'qa':
        imported(f.root, qa('Changed scientific basis'))
    elif change == 'preparation':
        previous = build_view(f.root)['m1_preparations'][0]['ref']
        p.update(previous_ref=previous, revision_reason='Further equipment check needed')
        p['items']['measurement'].update(status='missing', verification_refs=[], reason='Equipment changed')
        apply(f.root, 'm1.preparation.register', p)
    else:
        check_id = p['items']['measurement']['verification_refs'][0]['artifact_id']
        evidence_ref = store.read_head(f.root)['state']['m1_preparation_verifications'][check_id]['evidence_ref']
        verify(f, evidence_ref, outcome='rejected', rationale='New check rejects prior claim')
    f.head = store.read_head(f.root)
    before = f.head['id']
    with pytest.raises(ValueError): f.accept()
    assert store.read_head(f.root)['id'] == before
    status = handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert not status['gate_ready'] and status['manifest'] == issued['manifest']


def test_external_gate_shape_and_manifest_tampering_are_rejected(package):
    f, p = package
    issued = f.issue_package()
    gate = deepcopy(f.head['state']['gate_requirements'][issued['gate_id']])
    gate['corpus_ref'] = p['review_ref']
    from researchclaw.core.research_graph.handoffs import assess_native_handoff
    with pytest.raises(ValueError, match='gate_invalid'): assess_native_handoff(f.snapshot(), gate)
    before = f.snapshot()
    state = deepcopy(before['state'])
    state['handoff_manifests'][issued['manifest']['id']]['limitations'] = []
    changed = state['handoff_manifests'][issued['manifest']['id']]
    store.commit_record(f.root, expected_head=before['id'], command_id='forged-manifest', state=state,
        event={**store._VERSION,'type':'forged','payload':{}}, objects={changed['id']:store._canonical(changed)})
    with pytest.raises(ValueError): handoff_status(f.snapshot(), handoff_id=f.package_id)


def test_external_empirical_question_requires_receiving_verification_and_owner_transfer(package):
    from uuid import uuid4
    from researchclaw.core.research_graph.m1_nodes import current_node, _context
    from researchclaw.core.research_graph.councils import _record_ref
    from tests.codex_native.research_graph.test_m1_preparation_verification import complete_items
    f, p = package
    inputs = _context(f.snapshot())
    current, old_ref = current_node(inputs, 'review')
    f.binding = old_ref
    m1_owner = deepcopy(f.author)
    issue = f.issue(producer='author')
    issue['category'] = 'empirical'
    issue['target_refs'] = [current_node(inputs, 'hypothesize')[1]]
    f.publish(issue)
    with pytest.raises(ValueError, match='handoff_issue_unresolved'):
        f.issue_package()
    # Isolated fixture budget source has no dependency on the old review.
    budget_bytes = store._canonical({'scope':'Invented test budget', 'experiment_runs':1})
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id='fixture-budget',
        state=f.head['state'], event={**store._VERSION,'type':'fixture_budget','payload':{}},
        objects={'fixture/budget':budget_bytes})
    budget_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id='fixture/budget',
                      sha256=store._hash(budget_bytes))
    revision = {**deepcopy(f.artifact), **f.envelope(), 'attempt':str(uuid4()),
                'previous_ref':old_ref, 'revision_reason':'Carry empirical question with receiving obligation'}
    revision['content']['prior_issue_dispositions'] = [dict(issue_id=issue['id'], disposition='transfer_proposed',
        owner_assignment_id=m1_owner['id'], hypothesis_ids=['h1'], rationale='Needs an experiment', verification_refs=[])]
    revision['content']['open_questions'] = [dict(issue_id=issue['id'], question=issue['question'],
        method='Prespecified comparison', resolution_condition=issue['resolution_condition'],
        owner_assignment_id=m1_owner['id'], to_milestone='M2', budget_ref=budget_ref, limitations=['Untested'])]
    previous_preparation = build_view(f.root)['m1_preparations'][0]['ref']
    f.register(revision)
    council = f.council_payload(); council['council']['issue_ids'] = [issue['id']]
    f.apply('council.prepare', council)
    f.submitted = {phase:[] for phase in ('initial','response','final')}
    f.complete()
    p.update(review_ref=current_node(_context(f.snapshot()), 'review')[1],
             previous_ref=previous_preparation, revision_reason='Checks bound to reviewed empirical question')
    for item in p['items'].values(): item['owner_id'] = f.author['id']
    complete_items(f, p)
    apply(f.root, 'm1.preparation.register', p)
    f.head = store.read_head(f.root); f.account()
    issued = f.issue_package(); f.receiver()
    with pytest.raises(ValueError, match='handoff_verification_invalid'): f.accept()
    proposal = issued['transfer_proposals'][0]
    verification = {**f.envelope('receiver'), 'id':proposal['verification_id'], 'issue_ids':[issue['id']],
        'method':'experiment', 'question':issue['question'], 'input_refs':issued['verification_input_refs'],
        'acceptance_rule':issue['resolution_condition'], 'owner_assignment_id':f.receiver_assignment['id'],
        'budget_ref':budget_ref}
    f.apply('verification.prepare', {'verification':verification})
    verification_ref = _record_ref(_context(f.snapshot()), 'verifications', verification)
    f.account(); f.accept([verification_ref])
    accepted = handoff_status(f.snapshot(), handoff_id=f.package_id)
    assert not accepted['gate_ready'] and 'native_transfer_required' in accepted['reason_codes']
    event = {**f.envelope(m1_owner['actor_id']), 'issue_id':issue['id'], 'from_status':'open',
        'to_status':'transferred', 'actor_assignment_id':m1_owner['id'], 'rationale':'Receiver accepted obligation',
        'verification_refs':[], 'successor_ids':[], 'to_milestone':'M2', 'owner_assignment_id':f.receiver_assignment['id'],
        'verification_id':verification['id'], 'acceptance_event_id':accepted['transfer_acceptance_ids'][issue['id']]}
    f.apply('issue.event', {'issue':None, 'event':event})
    assert handoff_status(f.snapshot(), handoff_id=f.package_id)['gate_ready']
    assert f.head['state']['issues'][issue['id']] == issue
