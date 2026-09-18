"""Native non-node review work is recorded without fabricating node revisions."""
from copy import deepcopy

import pytest

from researchclaw.core.research_graph import store, work_accounting as accounting
from tests.codex_native.research_graph.test_m1_scope import Fixture, uid
from tests.codex_native.research_graph.test_issue_scopes import setup, council
from tests.codex_native.research_graph.test_source_intake import capture


def prepared(root, kind):
    if kind == 'issue_scope':
        f, _, proposal, ref = setup(root)
        council(f, proposal, ref)
        return f
    f = Fixture(root)
    f.register()
    f.apply('m1.source.capture', {'captures': [capture(b'first'), capture(b'second')]})
    refs = [dict(project_id=f.project, head_id=f.head['id'],
                 artifact_id='m1/intake/blobs/' + store._hash(data), sha256=store._hash(data))
            for data in (b'first', b'second')]
    payload = f.council_payload()
    payload['council'].update(node=kind, attempt=uid(), allowed_evidence_refs=refs)
    payload['review_session']['input_binding'] = refs[0]
    f.apply('council.prepare', payload)
    f.binding = refs[0]
    f.submitted = {phase: [] for phase in ('initial', 'response', 'final')}
    return f


@pytest.mark.parametrize('kind', ['issue_scope', 'source_analysis'])
def test_completed_non_node_council_has_real_inputs_and_can_be_accounted(tmp_path, kind):
    f = prepared(tmp_path, kind)
    f.complete(final='ready_with_limits')
    before = f.snapshot()
    sources = accounting.work_sources(before)
    source = next(s for s in sources if s['source_ref']['artifact_id'] == f.council['id'])
    assert source['recorded'] is False
    for source in sources:
        f.apply('m1.work.record', dict(record_id=uid(), **{k: source[k] for k in ('source_kind', 'source_ref')}))
    f.apply('work_ledger.refresh', {'ledger_id': uid()})
    record = next(r for r in f.head['state']['work_records'].values() if r['work']['node'] == kind)
    expected = [f.binding]
    expected.extend(r for r in f.council['allowed_evidence_refs'] if r not in expected)
    assert record['work']['input_refs'] == expected
    assert record['status'] == 'completed'
    assert record['resource_request'] == dict(returns=0, verification_runs=0, estimated_cost=None, cost_status='unknown')
    assert f.head['state']['m1_node_revisions'] == before['state']['m1_node_revisions']
    assert accounting.accounting_status(f.snapshot())['ready']
    assert all(s['recorded'] for s in accounting.work_sources(f.snapshot()))
    with pytest.raises(ValueError, match='work_source_already_recorded'):
        f.apply('m1.work.record', dict(record_id=uid(), **{k: source[k] for k in ('source_kind', 'source_ref')}))


@pytest.mark.parametrize('kind', ['issue_scope', 'source_analysis'])
def test_incomplete_non_node_council_is_not_completed_work(tmp_path, kind):
    f = prepared(tmp_path, kind)
    f.submit(0, 'initial')
    assert f.council['id'] not in {s['source_ref']['artifact_id'] for s in accounting.work_sources(f.snapshot())}


@pytest.mark.parametrize('kind', ['issue_scope', 'source_analysis'])
@pytest.mark.parametrize('tamper', ['preparation', 'submission', 'binding', 'bytes'])
def test_non_node_accounting_rejects_tampered_provenance(tmp_path, kind, tamper):
    f = prepared(tmp_path, kind)
    f.complete()
    snapshot = deepcopy(f.snapshot())
    if tamper == 'bytes':
        del snapshot['_issue_context']['objects'][store._hash(store._canonical(f.council))]
    else:
        collection, identity = ('council_submissions', f.submitted['final'][0]['artifact_id']) if tamper == 'submission' else ('councils', f.council['id'])
        first = next(old for _, old in snapshot['_issue_context']['history'] if identity in old['state'].get(collection, {}))
        if tamper == 'binding':
            first['state']['review_sessions'][f.session['id']]['input_binding'] = dict(f.binding, sha256='0' * 64)
        else:
            first['events'][-1]['type'] = 'forged_history'
    with pytest.raises(ValueError):
        accounting.work_sources(snapshot)


@pytest.mark.parametrize('final, status', [('revise', 'inconclusive'), ('defer', 'awaiting_input')])
@pytest.mark.parametrize('kind', ['issue_scope', 'source_analysis'])
def test_non_node_dissent_is_still_real_work(tmp_path, kind, final, status):
    f = prepared(tmp_path, kind)
    f.complete(final=final)
    snapshot = f.snapshot()
    inputs = accounting._context(snapshot)
    ref = accounting._record_ref(inputs, 'councils', f.council)
    record, _ = accounting._source(inputs, 'council', ref, uid())
    assert record['status'] == status


def test_scope_work_survives_later_impact_change(tmp_path):
    f = prepared(tmp_path, 'issue_scope')
    f.complete()
    before = accounting.work_sources(f.snapshot())
    from researchclaw.core.research_graph.issue_impacts import _FIELDS
    impact = next(iter(f.head['state']['issue_impacts'].values()))
    row = {key: impact[key] for key in _FIELDS}
    row['next_check'] = 'Changed current investigation'
    f.apply('issue.impact.record', {'assessments': [row]})
    assert accounting.work_sources(f.snapshot()) == before


def test_native_scope_council_with_wrong_proposal_owner_is_rejected(tmp_path):
    f, _, proposal, ref = setup(tmp_path)
    payload = f.council_payload(author='wrong-proposal-owner')
    payload['council'].update(node='issue_scope', attempt=proposal['id'],
        issue_ids=[r['issue_ref']['artifact_id'] for r in proposal['changes']])
    payload['review_session']['input_binding'] = ref
    f.apply('council.prepare', payload)
    f.binding = ref
    f.submitted = {phase: [] for phase in ('initial', 'response', 'final')}
    f.complete()
    with pytest.raises(ValueError, match='work_source_invalid'):
        accounting.work_sources(f.snapshot())


def test_source_review_cannot_use_an_m1_node_as_a_captured_source(tmp_path):
    f = Fixture(tmp_path)
    f.register()
    payload = f.council_payload()
    payload['council'].update(node='source_analysis', attempt=uid())
    f.apply('council.prepare', payload)
    f.submitted = {phase: [] for phase in ('initial', 'response', 'final')}
    f.complete()
    with pytest.raises(ValueError, match='work_source_invalid'):
        accounting.work_sources(f.snapshot())


@pytest.mark.parametrize('kind', ['issue_scope', 'source_analysis'])
def test_native_looking_final_cannot_bypass_phase_order(tmp_path, kind):
    f = prepared(tmp_path, kind)
    initial = f.submit(0, 'initial')
    forged = dict(initial, id=uid(), event_id=uid(), phase='final', recommendation='ready')
    state = deepcopy(f.head['state'])
    state['council_submissions'][forged['id']] = forged
    store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'council_submission_registered',
               'payload': dict(submission_id=forged['id'], session_id=f.session['id'], phase='final')},
        objects={forged['id']: store._canonical(forged)})
    with pytest.raises(ValueError, match='council_phase_invalid'):
        accounting.work_sources(f.snapshot())


@pytest.mark.parametrize('overlap', ['author', 'reviewer'])
def test_native_looking_preparation_cannot_fake_independent_reviewers(tmp_path, overlap):
    f = Fixture(tmp_path)
    f.register()
    f.apply('m1.source.capture', {'captures': [capture()]})
    digest = capture()['sha256']
    ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id='m1/intake/blobs/' + digest, sha256=digest)
    payload = f.council_payload()
    payload['council'].update(node='source_analysis', attempt=uid())
    payload['review_session']['input_binding'] = ref
    payload['assignments'][1]['actor_id'] = payload['assignments'][0 if overlap == 'author' else 2]['actor_id']
    state = deepcopy(f.head['state'])
    records = [('councils', payload['council']), ('review_sessions', payload['review_session']),
               *(('assignments', actor) for actor in payload['assignments'])]
    for collection, record in records:
        state.setdefault(collection, {})[record['id']] = record
    store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'council_prepared',
               'payload': dict(council_id=f.council['id'], session_id=f.session['id'])},
        objects={record['id']: store._canonical(record) for _, record in records})
    with pytest.raises(ValueError, match='council_assignment_invalid'):
        accounting.work_sources(f.snapshot())
