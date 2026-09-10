"""Reviewed preparation-only scope amendments never resolve scientific issues."""
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.councils import _record_ref
from researchclaw.core.research_graph.issues import _Inputs
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_scope import Fixture


def apply(f,op,payload):
    f.head=commands.apply_command(f.root,operation=op,payload=payload,
        expected_head=store.read_head(f.root)['id'],command_id=str(uuid4()))
    return f.head


def setup(root):
    f=Fixture(root);f.register();f.council_prepare();f.complete()
    scope_ref=f.node_ref()
    f.register(f.node('questions',input_refs={'scope':scope_ref}));f.council_prepare();f.complete()
    issue=f.issue();issue['blocking_scope']=[dict(kind='node',milestone='M1',target_id='questions')]
    f.publish(issue)
    entry=build_view(root)['issues'][0]
    impact=dict(issue_ref=entry['ref'],group_key='data',group_title='단위 확인',affected_sources=['data'],
        hypotheses=['H1'],held_work=['학습'],preparation_work=['질문 작성'],next_check='단위 확인',
        if_unresolved='학습 보류',owner_role='소재',rationale='질문과 실제 검증을 구분',producer_id='coordinator')
    apply(f,'issue.impact.record',{'assessments':[impact]})
    ref=build_view(root)['issue_impacts'][0]['ref']
    apply(f,'issue.scope.propose',{'impact_refs':[ref],'producer_id':'coordinator','rationale':'질문 작성만 진행'})
    proposal=next(iter(f.head['state']['issue_scope_proposals'].values()))
    inputs=_Inputs(commands.read_policy_snapshot(root))
    return f,issue,proposal,_record_ref(inputs,'issue_scope_proposals',proposal)


def test_proposal_does_not_change_blocking_scope(tmp_path):
    f,issue,proposal,ref=setup(tmp_path)
    from researchclaw.core.research_graph.issue_scopes import effective_scopes
    assert effective_scopes(_Inputs(f.snapshot()),issue)==issue['blocking_scope']
    before=f.head['id']
    with pytest.raises(ValueError):
        apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':str(uuid4())})
    assert store.read_head(f.root)['id']==before


def council(f,proposal,ref):
    payload=f.council_payload()
    payload['council'].update(node='issue_scope',attempt=proposal['id'],issue_ids=[r['issue_ref']['artifact_id'] for r in proposal['changes']])
    payload['review_session']['input_binding']=ref
    # Existing fixture's author is distinct from the coordinator proposal author.
    payload['assignments'][0]['actor_id']='coordinator'
    apply(f,'council.prepare',payload)
    f.binding=ref;f.submitted={p:[] for p in ('initial','response','final')}
    return payload['council']['id']


def test_complete_unanimous_review_moves_only_question_block_and_keeps_handoff_hold(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);cid=council(f,proposal,ref)
    before=f.head['id']
    with pytest.raises(ValueError,match='scope_review_required'):
        apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    assert store.read_head(f.root)['id']==before
    f.complete()
    apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    from researchclaw.core.research_graph.issue_scopes import effective_scopes
    scopes=effective_scopes(_Inputs(f.snapshot()),issue)
    assert dict(kind='node',milestone='M1',target_id='questions') not in scopes
    assert dict(kind='node',milestone='M1',target_id='review') in scopes
    assert dict(kind='handoff',milestone='M1',target_id='M2') in scopes
    from researchclaw.core.research_graph.m1_nodes import review_node
    assert review_node(f.snapshot(),'questions')['ready'] is True
    assert f.head['state']['issues'][issue['id']]==issue
    assert build_view(f.root)['issues'][0]['status']=='open'


def test_conditional_final_does_not_silently_grant_extra_conditions(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);cid=council(f,proposal,ref);f.complete(final='ready_with_limits')
    before=f.head['id']
    with pytest.raises(ValueError,match='scope_review_required'):
        apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    assert store.read_head(f.root)['id']==before


def test_changed_impact_restores_original_question_block(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);cid=council(f,proposal,ref);f.complete()
    apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    impact=next(iter(f.head['state']['issue_impacts'].values()))
    from researchclaw.core.research_graph.issue_impacts import _FIELDS
    row={k:impact[k] for k in _FIELDS};row['next_check']='새 전제 확인'
    apply(f,'issue.impact.record',{'assessments':[row]})
    from researchclaw.core.research_graph.issue_scopes import effective_scopes
    assert effective_scopes(_Inputs(f.snapshot()),issue)==issue['blocking_scope']
    from researchclaw.core.research_graph.m1_nodes import review_node
    assert 'blocking_issue_unresolved' in review_node(f.snapshot(),'questions')['reason_codes']


def test_scope_request_cannot_drop_review_or_handoff_protection(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);before=f.head['id']
    with pytest.raises(ValueError,match='scope_proposal_invalid'):
        apply(f,'issue.scope.propose',dict(impact_refs=[proposal['changes'][0]['impact_ref']],
            producer_id='coordinator',rationale='remove everything',replacement_scopes=[]))
    assert store.read_head(f.root)['id']==before


def test_question_revision_restores_scope_but_historical_view_keeps_applied_scope(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);cid=council(f,proposal,ref);f.complete()
    applied=apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    from researchclaw.core.research_graph.m1_nodes import current_node, _context
    scope_ref=current_node(_context(f.snapshot()),'scope')[1]
    previous=current_node(_context(f.snapshot()),'questions')[1]
    f.register(f.node('questions',input_refs={'scope':scope_ref},previous_ref=previous,revision_reason='새 연구 질문'))
    from researchclaw.core.research_graph.issue_scopes import effective_scopes
    assert effective_scopes(_Inputs(f.snapshot()),issue)==issue['blocking_scope']
    from researchclaw.core.research_graph.views import _load
    historic,_=_load(f.root,applied['id'])
    assert dict(kind='node',milestone='M1',target_id='questions') not in effective_scopes(_Inputs(historic),issue)


def test_reviewed_scope_allows_search_registration_without_reblocking_questions(tmp_path):
    f,issue,proposal,ref=setup(tmp_path)
    from researchclaw.core.research_graph.m1_nodes import current_node, _context, review_node
    inputs=_context(f.snapshot())
    question_artifact=f.artifact
    search=f.node('search',input_refs={n:current_node(inputs,n)[1] for n in ('scope','questions')},
        content={'queries':['measurement conditions'],'sources':['public repository'],
                 'inclusion_criteria':['relevant methods'],'exclusion_criteria':['unrelated']})
    before=f.head['id']
    with pytest.raises(ValueError,match='m1_upstream_review_required'):
        f.register(search)
    assert store.read_head(f.root)['id']==before
    f.artifact=question_artifact
    cid=council(f,proposal,ref);f.complete()
    apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    f.register(search)
    assert review_node(f.snapshot(),'questions')['ready'] is True
    assert f.head['state']['m1_node_heads']['search']==search['id']


def test_final_without_exact_proposal_evidence_does_not_activate_scope(tmp_path):
    f,issue,proposal,ref=setup(tmp_path);cid=council(f,proposal,ref)
    for phase in ('initial','response','final'):
        for index in range(3):
            extras={'recommendation':'ready'} if phase=='final' else {}
            if phase=='final' and index==0:extras['evidence_refs']=[]
            f.submit(index,phase,**extras)
    before=f.head['id']
    with pytest.raises(ValueError,match='scope_review_required'):
        apply(f,'issue.scope.apply',{'proposal_ref':ref,'council_id':cid})
    assert store.read_head(f.root)['id']==before
