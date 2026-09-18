"""B5a records preparation gaps; synthetic fixtures confer no readiness."""
from copy import deepcopy

import pytest

from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_evidence_basis import ready
from tests.codex_native.research_graph.test_m1_external_inputs import external, artifact
from tests.codex_native.research_graph.test_external_evidence import apply, imported, qa

CATEGORIES = ('design_analysis', 'data_lineage', 'material', 'manufacturing',
              'measurement', 'repetition', 'resources_permissions')
OPERATION = 'm1.preparation.register'


@pytest.fixture
def preparation(external):
    f, p, basis = external
    refs = {}
    for node in ('synthesize', 'hypothesize', 'review'):
        f.register(artifact(f, p, basis, node, refs))
        if node != 'review':
            f.council_prepare(); f.complete()
        refs[node] = f.node_ref()
    decisions = {}
    for kind in ('design', 'data_lineage'):
        apply(f.root, 'external.decision.record', dict(review_ref=p['review_refs'][0],
            title=kind, conclusion='Preparation remains missing', rationale='No execution evidence',
            limitations=['Unverified'], submission_refs=[], prior_ref=None, producer_id='coordinator'))
        decisions[kind] = next(row['ref'] for row in build_view(f.root)['external_decisions']
                              if row['record']['title'] == kind)
    payload = dict(review_ref=refs['review'], decision_refs=decisions,
        items={category: dict(status='missing', reason='Awaiting actual confirmation',
                             owner_id=f.author['id'], verification_refs=[]) for category in CATEGORIES},
        previous_ref=None, revision_reason=None, producer_id='coordinator')
    return f, payload


def test_draft_records_exact_gaps_without_handoff_authority(preparation):
    f, p = preparation
    before = store.read_head(f.root)
    result = apply(f.root, OPERATION, p)
    row = build_view(f.root)['m1_preparations'][0]
    assert row['record']['items'] == p['items']
    assert row['record']['decision_refs'] == p['decision_refs']
    assert row['current'] and not row['preparation_ready']
    assert row['missing_items'] == list(CATEGORIES)
    assert row['reason_codes'] == ['preparation_draft_only', 'preparation_items_missing']
    assert row['external_handoff_supported']
    assert all(result['state'][key] == value for key, value in before['state'].items())


@pytest.mark.parametrize('change', ['missing_category', 'synthetic_verification', 'tampered_decision', 'wrong_review', 'empty_reason'])
def test_invalid_draft_is_atomic(preparation, change):
    f, p = preparation
    if change == 'missing_category': del p['items']['measurement']
    elif change == 'synthetic_verification':
        p['items']['measurement'].update(status='verified', verification_refs=[p['review_ref']])
    elif change == 'tampered_decision': p['decision_refs']['design']['sha256'] = '0' * 64
    elif change == 'wrong_review': p['review_ref'] = p['decision_refs']['design']
    else: p['items']['measurement']['reason'] = ''
    before = store.read_head(f.root)['id']
    with pytest.raises(ValueError, match='preparation_'):
        apply(f.root, OPERATION, p)
    assert store.read_head(f.root)['id'] == before


def test_qa_updates_stale_current_preparation_preserving_historical_view(preparation):
    f, p = preparation
    first = apply(f.root, OPERATION, p)
    imported(f.root, qa('Changed provenance'))
    row = build_view(f.root)['m1_preparations'][0]
    assert not row['current'] and not row['preparation_ready']
    assert build_view(f.root, head_id=first['id'])['m1_preparations'][0]['current']
    with pytest.raises(ValueError, match='preparation_'):
        apply(f.root, OPERATION, p)


def test_revision_keeps_prior_draft_and_rejects_forks(preparation):
    f, p = preparation
    apply(f.root, OPERATION, p)
    old = build_view(f.root)['m1_preparations'][0]
    p.update(previous_ref=old['ref'], revision_reason='Clarify missing measurement')
    p['items']['measurement']['reason'] = 'Operator and calibration not known'
    apply(f.root, OPERATION, p)
    rows = build_view(f.root)['m1_preparations']
    assert len(rows) == 2 and sum(row['superseded'] for row in rows) == 1
    with pytest.raises(ValueError, match='preparation_previous'):
        apply(f.root, OPERATION, p)


@pytest.mark.parametrize('tamper', ['clear', 'edit'])
def test_tampered_history_is_rejected(preparation, tamper):
    f, p = preparation
    receipt = apply(f.root, OPERATION, p)
    records = deepcopy(receipt['state']['m1_preparations'])
    if tamper == 'clear': records = {}
    else: next(iter(records.values()))['items']['measurement']['status'] = 'verified'
    store.commit_record(f.root, expected_head=receipt['id'], command_id='tamper',
        state={**receipt['state'], 'm1_preparations': records},
        event={**store._VERSION, 'type': 'forged', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='preparation_native'):
        build_view(f.root)


def test_not_applicable_declaration_is_still_unverified(preparation):
    f, p = preparation
    for item in p['items'].values():
        item.update(status='not_applicable', reason='Coordinator proposes an exemption')
    apply(f.root, OPERATION, p)
    row = build_view(f.root)['m1_preparations'][0]
    assert row['missing_items'] == [] and not row['preparation_ready']
    assert 'preparation_verification_required' in row['reason_codes']
    assert not row['review_ready'] and 'council_required' in row['review_reason_codes']


def test_unknown_owner_is_rejected(preparation):
    from uuid import uuid4
    f, p = preparation
    p['items']['measurement']['owner_id'] = str(uuid4())
    with pytest.raises(ValueError, match='preparation_'):
        apply(f.root, OPERATION, p)
