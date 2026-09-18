"""Typed preparation evidence fixtures are synthetic and never confer real readiness."""
import base64
from copy import deepcopy
import pytest
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_preparation import preparation, CATEGORIES
from tests.codex_native.research_graph.test_m1_external_inputs import external
from tests.codex_native.research_graph.test_m1_evidence_basis import ready
from tests.codex_native.research_graph.test_external_evidence import apply, imported, qa


def ref(receipt, collection):
    record = receipt['state'][collection][receipt['events'][-1]['payload']['record_id']]
    return dict(project_id=record['project_id'], head_id=receipt['id'], artifact_id=record['id'], sha256=store._hash(store._canonical(record)))


def capture(f, p, category='measurement', disposition='verified'):
    raw = b'Synthetic preparation source: explicit fixture conditions and exemption scope.'
    payload = dict(review_ref=p['review_ref'], decision_refs=p['decision_refs'], category=category,
        owner_id=p['items'][category]['owner_id'], disposition=disposition, source_kind='document',
        source_locator='fixture://conditions', source_version='1', content_base64=base64.b64encode(raw).decode(),
        sha256=store._hash(raw), producer_id=f.author['actor_id'])
    return apply(f.root, 'm1.preparation.evidence.capture', payload)


def verify(f, evidence_ref, **changes):
    from researchclaw.core.research_graph.m1_preparation_verification import CRITERIA
    record = store.read_head(f.root)['state'].get('m1_preparation_evidence', {}).get(evidence_ref['artifact_id'])
    keys = ('scope_exemption',) if record and record['disposition'] == 'not_applicable' else CRITERIA[record['category']] if record else ()
    payload = dict(evidence_ref=evidence_ref, reviewer_id=f.reviewers[0]['id'],
        outcome='confirmed', checks={key: dict(result='pass', excerpt='explicit fixture conditions') for key in keys},
        excerpt='explicit fixture conditions and exemption scope', rationale='Checked the source against this item',
        producer_id=f.reviewers[0]['actor_id'])
    payload.update(changes)
    return apply(f.root, 'm1.preparation.evidence.verify', payload)


def complete_items(f, p):
    for category in CATEGORIES:
        disposition = 'not_applicable' if category == 'manufacturing' else 'verified'
        evidence = capture(f, p, category, disposition)
        checked = verify(f, ref(evidence, 'm1_preparation_evidence'))
        p['items'][category].update(status=disposition, verification_refs=[ref(checked, 'm1_preparation_verifications')])
    return p


def test_public_typed_flow_captures_bytes_and_checks_all_items_without_synthetic_authority(preparation):
    f, p = preparation
    complete_items(f, p)
    apply(f.root, 'm1.preparation.register', p)
    row = build_view(f.root)['m1_preparations'][0]
    assert row['current'] and row['missing_items'] == []
    assert not row['preparation_ready']
    assert 'preparation_synthetic_evidence' in row['reason_codes']
    assert 'preparation_draft_only' not in row['reason_codes']


@pytest.mark.parametrize('change', ['same_actor', 'excerpt', 'stale', 'fake_ref'])
def test_verification_rejects_invalid_binding_atomically(preparation, change):
    f, p = preparation
    reference = ref(capture(f, p), 'm1_preparation_evidence')
    changes = {}
    if change == 'same_actor': changes.update(reviewer_id=f.author['id'], producer_id=f.author['actor_id'])
    elif change == 'excerpt': changes['excerpt'] = 'not in source'
    elif change == 'stale': imported(f.root, qa('Updated QA'))
    else: reference = p['review_ref']
    before = store.read_head(f.root)['id']
    with pytest.raises(ValueError, match='preparation_'): verify(f, reference, **changes)
    assert store.read_head(f.root)['id'] == before


def test_wrong_item_and_untyped_refs_cannot_grant_status(preparation):
    f, p = preparation
    checked = verify(f, ref(capture(f, p), 'm1_preparation_evidence'))
    p['items']['material'].update(status='verified', verification_refs=[ref(checked, 'm1_preparation_verifications')])
    with pytest.raises(ValueError, match='preparation_'): apply(f.root, 'm1.preparation.register', p)


def test_typed_history_edit_is_rejected(preparation):
    f, p = preparation
    complete_items(f, p)
    receipt = apply(f.root, 'm1.preparation.register', p)
    records = deepcopy(receipt['state']['m1_preparation_verifications'])
    next(iter(records.values()))['rationale'] = 'forged'
    store.commit_record(f.root, expected_head=receipt['id'], command_id='forge-typed',
        state={**receipt['state'], 'm1_preparation_verifications': records},
        event={**store._VERSION, 'type': 'forged', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='preparation_'): build_view(f.root)


@pytest.mark.parametrize('change', ['missing_check', 'failed_check', 'rejected', 'same_actor_alias'])
def test_required_checks_and_independent_actor(preparation, change):
    f, p = preparation
    source = ref(capture(f, p), 'm1_preparation_evidence')
    changes = {}
    if change in ('missing_check', 'failed_check'):
        from researchclaw.core.research_graph.m1_preparation_verification import CRITERIA
        checks = {key: dict(result='pass', excerpt='explicit fixture conditions') for key in CRITERIA['measurement']}
        if change == 'missing_check': del checks['calibration']
        else: checks['calibration']['result'] = 'fail'
        changes['checks'] = checks
    elif change == 'rejected':
        checked = verify(f, source, outcome='rejected')
        p['items']['measurement'].update(status='verified', verification_refs=[ref(checked, 'm1_preparation_verifications')])
        with pytest.raises(ValueError, match='preparation_'): apply(f.root, 'm1.preparation.register', p)
        return
    else:
        receipt = store.read_head(f.root)
        assignments = deepcopy(receipt['state']['assignments'])
        assignments[f.reviewers[0]['id']]['actor_id'] = f.author['actor_id']
        row = assignments[f.reviewers[0]['id']]
        store.commit_record(f.root, expected_head=receipt['id'], command_id='actor-alias',
            state={**receipt['state'], 'assignments': assignments},
            event={**store._VERSION, 'type': 'fixture_actor_alias', 'payload': {}},
            objects={row['id']: store._canonical(row)})
        changes['producer_id'] = f.author['actor_id']
    with pytest.raises(ValueError, match='preparation_'): verify(f, source, **changes)


@pytest.fixture
def prepared_real(tmp_path, monkeypatch):
    """Invented scientific data: real label exercises production contract only."""
    from tests.codex_native.research_graph import test_m1_evidence_basis as basis_tests
    from tests.codex_native.research_graph.test_m1_scope import Fixture
    from researchclaw.core.research_graph import commands
    class RealFixture(Fixture):
        def __init__(self, root):
            self.root = root
            self.head = commands.init_project(root, topic='Isolated contract fixture; invented science', content_origin='real')
            self.project = self.head['state']['project_id']
            self.artifact = self.node()
        def envelope(self, producer='author'):
            return {**super().envelope(producer), 'content_origin': 'real'}
    with monkeypatch.context() as patch:
        patch.setattr(basis_tests, 'Fixture', RealFixture)
        basis = ready.__wrapped__(tmp_path)
    external_data = external.__wrapped__(basis)
    f, p = preparation.__wrapped__(external_data)
    f.head = store.read_head(f.root)
    f.council_prepare(); f.complete()
    for item in p['items'].values(): item['owner_id'] = f.author['id']
    complete_items(f, p)
    apply(f.root, 'm1.preparation.register', p)
    f.head = store.read_head(f.root)
    return f, p


def test_real_label_contract_can_be_preparation_ready(prepared_real):
    f, p = prepared_real
    row = build_view(f.root)['m1_preparations'][0]
    assert row['preparation_ready'] and row['review_ready']


def test_later_rejection_invalidates_old_pass(preparation):
    f, p = preparation
    evidence = ref(capture(f, p), 'm1_preparation_evidence')
    passed = verify(f, evidence)
    verify(f, evidence, outcome='rejected')
    p['items']['measurement'].update(status='verified', verification_refs=[ref(passed, 'm1_preparation_verifications')])
    with pytest.raises(ValueError, match='preparation_'): apply(f.root, 'm1.preparation.register', p)


def test_duplicate_payload_cannot_poison_replay(preparation):
    f, p = preparation
    capture(f, p)
    before = store.read_head(f.root)['id']
    with pytest.raises(ValueError, match='preparation_'): capture(f, p)
    assert store.read_head(f.root)['id'] == before


def test_source_version_refresh_invalidates_old_verification(preparation):
    f, p = preparation
    first = capture(f, p)
    evidence = ref(first, 'm1_preparation_evidence')
    passed = verify(f, evidence)
    source = first['state']['m1_preparation_evidence'][evidence['artifact_id']]
    from researchclaw.core.research_graph.m1_preparation_verification import _CAPTURE
    updated = {key: source[key] for key in _CAPTURE}
    updated['source_version'] = '2'
    apply(f.root, 'm1.preparation.evidence.capture', updated)
    with pytest.raises(ValueError, match='preparation_evidence_superseded'): verify(f, evidence, rationale='Recheck old version')
    p['items']['measurement'].update(status='verified', verification_refs=[ref(passed, 'm1_preparation_verifications')])
    with pytest.raises(ValueError, match='preparation_'): apply(f.root, 'm1.preparation.register', p)


def test_typed_collection_cannot_be_cleared_without_preparation(preparation):
    f, p = preparation
    receipt = capture(f, p)
    store.commit_record(f.root, expected_head=receipt['id'], command_id='clear-source',
        state={**receipt['state'], 'm1_preparation_evidence': {}},
        event={**store._VERSION, 'type': 'forged', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='preparation_'): build_view(f.root)
