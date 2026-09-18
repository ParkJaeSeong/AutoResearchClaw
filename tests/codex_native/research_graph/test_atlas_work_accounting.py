"""Atlas evidence councils remain authenticated work without a fake M1 node."""
from copy import deepcopy

import pytest

from researchclaw.core.research_graph import store, work_accounting as accounting
from tests.codex_native.research_graph.test_m1_scope import Fixture, uid
from tests.codex_native.research_graph.test_external_evidence import imported, qa, review_payload


def prepared(root, *, wrong_author=False, extra_input=False):
    f=Fixture(root);f.register();payload=f.council_payload()
    f.head=imported(root, producer_id='author')
    evidence=next(iter(f.head['state']['external_evidence'].values()))
    evidence_ref=dict(project_id=f.project,head_id=f.head['id'],artifact_id=evidence['id'],sha256=store._hash(store._canonical(evidence)))
    p=review_payload(evidence_ref);p['producer_id']='other' if wrong_author else 'author'
    f.apply('external.review.record',p)
    review=next(iter(f.head['state']['external_reviews'].values()))
    f.binding=dict(project_id=f.project,head_id=f.head['id'],artifact_id=review['id'],sha256=store._hash(store._canonical(review)))
    payload['review_session']['input_binding']=f.binding
    payload['council'].update(node='atlas-evidence-review',attempt=uid(),producer_id='author',allowed_evidence_refs=[evidence_ref])
    if extra_input:payload['council']['allowed_evidence_refs'].append(f.node_ref())
    f.apply('council.prepare',payload);f.submitted={p:[] for p in ('initial','response','final')}
    return f,evidence


@pytest.mark.parametrize('final,status',[('ready','completed'),('ready_with_limits','completed'),('revise','inconclusive'),('defer','awaiting_input')])
def test_atlas_work_is_recorded_once_with_unknown_cost_and_preserved_inputs(tmp_path,final,status):
    f,_=prepared(tmp_path);f.complete(final=final)
    sources=accounting.work_sources(f.snapshot());assert len(sources)==1
    payload=dict(record_id=uid(),source_kind='council',source_ref=sources[0]['source_ref'])
    f.apply('m1.work.record',payload)
    record=f.head['state']['work_records'][payload['record_id']]
    assert record['status']==status
    assert record['work']['input_refs']==[f.binding,*f.council['allowed_evidence_refs']]
    assert record['resource_request']==dict(returns=0,verification_runs=0,estimated_cost=None,cost_status='unknown')
    assert accounting.work_sources(f.snapshot())[0]['recorded']
    with pytest.raises(ValueError,match='work_source_already_recorded'):
        f.apply('m1.work.record',dict(payload,record_id=uid()))
    f.apply('work_ledger.refresh',dict(ledger_id=uid()))
    assert accounting.accounting_status(f.snapshot())['ready']
    assert len(f.head['state']['m1_node_revisions'])==1


def test_new_qa_version_does_not_rewrite_completed_historical_work(tmp_path):
    f,_=prepared(tmp_path);f.complete()
    before=accounting.work_sources(f.snapshot())
    f.head=imported(tmp_path,qa('New answer'),producer_id='author')
    assert accounting.work_sources(f.snapshot())==before


def test_unfinished_atlas_council_does_not_become_completed_work(tmp_path):
    f,_=prepared(tmp_path);f.submit(0,'initial')
    assert accounting.work_sources(f.snapshot())==[]


def test_production_atlas_council_path_keeps_distinct_research_question(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_council import run_council
    from researchclaw.core.research_graph.commands import read_policy_snapshot
    from tests.codex_native.research_graph.test_atlas_question import prepared as atlas_prepared
    session, _, question = atlas_prepared(tmp_path)
    ask_research_question(session, 'accounting-test', question)
    def reviewer(role, phase, packet, material, directory):
        return dict(answer=dict(rationale='Synthetic review for accounting',recommendation='defer' if phase=='final' else None),host_id='synthetic',model_id='synthetic')
    result=run_council(session,'accounting-test',reviewer)
    snapshot=read_policy_snapshot(tmp_path)
    sources=accounting.work_sources(snapshot)
    source=next(s for s in sources if s['source_ref']['artifact_id']==result['council_id'])
    record,_=accounting._source(accounting._context(snapshot),'council',source['source_ref'],uid())
    assert record['status']=='awaiting_input'
    refs=record['work']['input_refs']
    assert len(refs)==3
    assert len({r['artifact_id'] for r in refs})==3
    council=snapshot['state']['councils'][result['council_id']]
    review_session=snapshot['state']['review_sessions'][council['session_id']]
    author=snapshot['state']['assignments'][council['author_assignment_ids'][0]]
    for allowed in [council['allowed_evidence_refs'][:1], [refs[0], refs[1]]]:
        changed={**council,'allowed_evidence_refs':allowed}
        with pytest.raises(ValueError,match='work_source_invalid'):
            accounting._atlas_review_input(snapshot,changed,review_session,author)


@pytest.mark.parametrize('change',['wrong_author','extra_input'])
def test_atlas_input_must_match_the_authored_review(tmp_path,change):
    f,_=prepared(tmp_path,**{change:True});f.complete()
    with pytest.raises(ValueError,match='work_source_invalid'):accounting.work_sources(f.snapshot())


@pytest.mark.parametrize('tamper',['raw_bytes','review_event','submission_event','review_bytes'])
def test_atlas_accounting_rejects_tampered_sources_and_history(tmp_path,tamper):
    f,evidence=prepared(tmp_path);f.complete();snapshot=deepcopy(f.snapshot())
    if tamper=='raw_bytes':snapshot['_issue_context']['objects'][evidence['sha256']]=b'wrong bytes'
    elif tamper=='review_bytes':snapshot['_issue_context']['objects'][f.binding['sha256']]=b'wrong review'
    else:
        collection,identity=('external_reviews',f.binding['artifact_id']) if tamper=='review_event' else ('council_submissions',f.submitted['final'][0]['artifact_id'])
        first=next(old for _,old in snapshot['_issue_context']['history'] if identity in old['state'].get(collection,{}))
        first['events'][-1]['type']='forged_history'
    with pytest.raises(ValueError):accounting.work_sources(snapshot)
