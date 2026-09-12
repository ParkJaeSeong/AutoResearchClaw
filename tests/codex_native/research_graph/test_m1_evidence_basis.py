"""B1 uses actual commands; synthetic research judgments only."""
from copy import deepcopy
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_scope import Fixture
from tests.codex_native.research_graph.test_external_evidence import imported, apply, review_payload, qa

@pytest.fixture
def ready(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete()
    f.register(f.node('questions', input_refs={'scope': f.node_ref()}))
    question = f.node_ref()
    imported(tmp_path)
    evidence = build_view(tmp_path)['external_evidence'][0]['ref']
    apply(tmp_path, 'external.review.record', review_payload(evidence))
    review = build_view(tmp_path)['external_reviews'][0]['ref']
    payload = dict(question_ref=question, question_text='Which method reproduces the gain?',
        review_refs=[review], claims=[dict(claim_id='c1', statement='Compare the methods',
            evidence_ref=evidence, review_ref=review, basis_kind='pilot_inference',
            qa_excerpt='First answer', rationale='A scoped inference', intended_use='hypothesis review',
            limitations=['Not empirical proof'])], coverage=dict(covered='Method comparison', missing='Measurements',
            decision_impact='Design only'), limitations=['Declared provenance'], previous_ref=None,
        revision_reason=None, producer_id='coordinator')
    return f, payload

def test_register_replay_preserves_prior_state_and_exposes_claim(ready):
    f,p = ready; before=store.read_head(f.root)
    result=apply(f.root,'m1.evidence_basis.register',p,command_id='basis-1')
    assert all(result['state'][k]==v for k,v in before['state'].items())
    assert apply(f.root,'m1.evidence_basis.register',p,expected=before['id'],command_id='basis-1')['id']==result['id']
    row=build_view(f.root)['m1_evidence_bases'][0]
    assert row['current'] and not row['superseded']
    assert row['record']['claims']==p['claims']
    assert row['claims'][0]['record']['statement']=='Compare the methods'
    assert not build_view(f.root)['approvals']

@pytest.mark.parametrize('change', ['excerpt','use','question','ref','empty','kind','extra','duplicate','coverage','review'])
def test_invalid_basis_is_atomic(ready,change):
    f,p=ready
    if change=='excerpt': p['claims'][0]['qa_excerpt']='Invented text'
    elif change=='use': p['claims'][0]['intended_use']='direct measurement'
    elif change=='question': p['question_text']='An unrelated question'
    elif change=='ref': p['question_ref']['sha256']='0'*64
    elif change=='empty': p['claims']=[]
    elif change=='kind': p['claims'][0]['basis_kind']='author_verified'
    elif change=='extra': p['ready']=True
    elif change=='duplicate': p['claims']*=2
    elif change=='coverage': p['coverage']['missing']=''
    elif change=='review': p['claims'][0]['review_ref']['artifact_id']='missing'
    before=store.read_head(f.root)['id']
    with pytest.raises(ValueError,match='evidence_basis'): apply(f.root,'m1.evidence_basis.register',p)
    assert store.read_head(f.root)['id']==before

def test_new_qa_invalidates_current_inputs_but_not_history(ready):
    f,p=ready; first=apply(f.root,'m1.evidence_basis.register',p)
    imported(f.root,qa('Second answer'))
    row=build_view(f.root)['m1_evidence_bases'][0]
    assert not row['current'] and 'evidence_basis_qa_updated' in row['reason_codes']
    assert build_view(f.root,head_id=first['id'])['m1_evidence_bases'][0]['current']
    with pytest.raises(ValueError,match='evidence_basis_qa_updated'): apply(f.root,'m1.evidence_basis.register',p)

def test_revision_keeps_original_and_rejects_fork(ready):
    f,p=ready; apply(f.root,'m1.evidence_basis.register',p)
    old=build_view(f.root)['m1_evidence_bases'][0]
    p.update(previous_ref=old['ref'],revision_reason='Clarify inference')
    p['claims'][0]['statement']='Scoped method comparison'
    apply(f.root,'m1.evidence_basis.register',p)
    rows=build_view(f.root)['m1_evidence_bases']; assert len(rows)==2
    assert next(r for r in rows if r['record']['id']==old['record']['id'])['superseded']
    with pytest.raises(ValueError,match='evidence_basis_previous'): apply(f.root,'m1.evidence_basis.register',p)

def test_alternate_ancestor_reference_cannot_fork_revision(ready):
    f,p=ready; apply(f.root,'m1.evidence_basis.register',p)
    old=build_view(f.root)['m1_evidence_bases'][0]
    p.update(previous_ref=old['ref'],revision_reason='Second version')
    p['claims'][0]['statement']='Second statement'
    second=apply(f.root,'m1.evidence_basis.register',p)
    p['previous_ref']={**old['ref'],'head_id':second['id']}
    p['claims'][0]['statement']='Attempted fork'
    with pytest.raises(ValueError,match='evidence_basis_previous'): apply(f.root,'m1.evidence_basis.register',p)

@pytest.mark.parametrize('status',['hold','exclude'])
def test_held_review_cannot_support_claim(ready,status):
    f,p=ready
    review=review_payload(p['claims'][0]['evidence_ref']);review.update(status=status,allowed_uses=[])
    receipt=apply(f.root,'external.review.record',review)
    identity=receipt['events'][-1]['payload']['record_id']
    r=next(r['ref'] for r in build_view(f.root)['external_reviews'] if r['record']['id']==identity)
    p['review_refs']=[r];p['claims'][0]['review_ref']=r
    with pytest.raises(ValueError,match='evidence_basis_use_not_allowed'): apply(f.root,'m1.evidence_basis.register',p)

def test_question_revision_marks_basis_stale_and_can_be_explicitly_rebased(ready):
    f,p=ready; first=apply(f.root,'m1.evidence_basis.register',p)
    old=build_view(f.root)['m1_evidence_bases'][0]
    f.head=store.read_head(f.root)
    question=deepcopy(f.artifact);question.update(id=str(uuid4()),
        event_id=str(uuid4()),attempt=str(uuid4()),
        previous_ref=p['question_ref'],revision_reason='Clarify question')
    question['content']['questions'][0]['question']='Which comparison is useful?'
    f.register(question)
    row=build_view(f.root)['m1_evidence_bases'][0]
    assert row['reason_codes']==['evidence_basis_question_updated']
    p.update(question_ref=f.node_ref(),question_text='Which comparison is useful?',
             previous_ref=old['ref'],revision_reason='Bind revised question')
    apply(f.root,'m1.evidence_basis.register',p)
    assert sum(r['current'] and not r['superseded'] for r in build_view(f.root)['m1_evidence_bases'])==1
    assert build_view(f.root,head_id=first['id'])['m1_evidence_bases'][0]['current']

def test_unselected_review_is_disclosed_without_auto_selection(ready):
    f,p=ready;apply(f.root,'m1.evidence_basis.register',p)
    review=review_payload(p['claims'][0]['evidence_ref']);review.update(status='hold',allowed_uses=[])
    apply(f.root,'external.review.record',review)
    row=build_view(f.root)['m1_evidence_bases'][0]
    assert len(row['review_candidates'])==1
    assert row['record']['review_refs']==p['review_refs']

def test_generic_store_record_is_not_a_native_basis(ready):
    f,p=ready;receipt=apply(f.root,'m1.evidence_basis.register',p)
    record=deepcopy(next(iter(receipt['state']['m1_evidence_bases'].values())))
    record['claims'][0]['statement']='Forged update'
    store.commit_record(f.root,expected_head=receipt['id'],command_id='forge',
        state={**receipt['state'],'m1_evidence_bases':{record['id']:record}},
        event={**store._VERSION,'type':'forged','payload':{}},objects={record['id']:store._canonical(record)})
    with pytest.raises(ValueError,match='evidence_basis_'):build_view(f.root)

def test_foreign_question_and_missing_revision_reason_are_atomic(ready,tmp_path):
    f,p=ready;apply(f.root,'m1.evidence_basis.register',p)
    old=build_view(f.root)['m1_evidence_bases'][0]
    p['previous_ref']=old['ref']
    before=store.read_head(f.root)['id']
    with pytest.raises(ValueError,match='evidence_basis_previous_reason'):apply(f.root,'m1.evidence_basis.register',p)
    p['revision_reason']='Test foreign reference';p['question_ref']['project_id']=str(uuid4())
    with pytest.raises(ValueError,match='evidence_basis_question'):apply(f.root,'m1.evidence_basis.register',p)
    assert store.read_head(f.root)['id']==before

def test_cli_apply_inspect_and_claim_raw_are_public(ready,tmp_path,capsys):
    import json
    from researchclaw.codex.cli import main
    from researchclaw.core.research_graph.views import read_artifact
    f,p=ready;path=tmp_path/'basis.json';path.write_text(json.dumps(p))
    assert main(['research','apply',str(f.root),'--operation','m1.evidence_basis.register',
        '--payload',str(path),'--expected-head',store.read_head(f.root)['id'],'--command-id','cli-basis','--json'])==0
    capsys.readouterr()
    assert main(['research','inspect',str(f.root),'--json'])==0
    view=json.loads(capsys.readouterr().out);row=view['m1_evidence_bases'][0]
    assert row['current'] and len(row['claims'])==1
    raw=read_artifact(f.root,artifact_id=row['claims'][0]['artifact_id'])
    assert json.loads(raw)['qa_excerpt']=='First answer'

def test_review_at_later_ancestor_is_still_disclosed(ready):
    f,p=ready;basis=apply(f.root,'m1.evidence_basis.register',p)
    ref={**p['claims'][0]['evidence_ref'],'head_id':basis['id']}
    review=review_payload(ref);review.update(status='hold',allowed_uses=[])
    apply(f.root,'external.review.record',review)
    assert len(build_view(f.root)['m1_evidence_bases'][0]['review_candidates'])==1

def test_clearing_collection_cannot_hide_native_history(ready):
    f,p=ready;receipt=apply(f.root,'m1.evidence_basis.register',p)
    store.commit_record(f.root,expected_head=receipt['id'],command_id='clear',
        state={**receipt['state'],'m1_evidence_bases':{}},
        event={**store._VERSION,'type':'forged','payload':{}},objects={})
    with pytest.raises(ValueError,match='evidence_basis_native_invalid'):build_view(f.root)

def test_selected_review_at_later_head_is_not_an_unselected_candidate(ready):
    f,p=ready
    imported(f.root,qa(identity='unrelated-qa'))
    later={**p['review_refs'][0],'head_id':store.read_head(f.root)['id']}
    p['review_refs']=[later];p['claims'][0]['review_ref']=later
    apply(f.root,'m1.evidence_basis.register',p)
    assert build_view(f.root)['m1_evidence_bases'][0]['review_candidates']==[]
