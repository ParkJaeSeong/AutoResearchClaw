"""Versioned work triage cannot silently clear issue or milestone gates."""
from copy import deepcopy
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_scope import Fixture


def setup(root):
    f=Fixture(root);f.register();f.council_prepare();f.publish(f.issue())
    entry=build_view(root)['issues'][0]
    row=dict(issue_ref=entry['ref'],group_key='H1-data',group_title='측정 조건 확인',
        affected_sources=['EC table'],hypotheses=['H1'],held_work=['가설 평가 학습'],
        preparation_work=['자료 사용표 작성'],next_check='단위 출처 대조',
        if_unresolved='해당 값을 쓰는 비교 보류',owner_role='소재 검토',
        rationale='자료 준비와 실제 평가의 선행조건을 구분',producer_id='coordinator')
    return f,row


def apply(f,rows):
    return commands.apply_command(f.root,operation='issue.impact.record',payload={'assessments':rows},
        expected_head=store.read_head(f.root)['id'],command_id=str(__import__('uuid').uuid4()))


def test_impact_preserves_blocking_policy_and_original_issue(tmp_path):
    f,row=setup(tmp_path);before=deepcopy(store.read_head(f.root))
    result=apply(f,[row]);view=build_view(f.root)
    assert {k:v for k,v in result['state'].items() if k!='issue_impacts'}==before['state']
    assert view['issues'][0]['status']=='open'
    assert view['nodes']==build_view(f.root,head_id=before['id'])['nodes']
    assert len(view['issue_impacts'])==1
    assert view['issue_impacts'][0]['current'] is True
    assert view['issue_impacts'][0]['record']['assessment_kind']=='coordinator_proposal'


def test_new_assessment_preserves_old_and_exact_retry_deduplicates(tmp_path):
    f,row=setup(tmp_path);first=apply(f,[row]);apply(f,[row])
    assert len(build_view(f.root)['issue_impacts'])==1
    row['next_check']='핵심 단위를 원 논문에서 확인'
    apply(f,[row]);entries=build_view(f.root)['issue_impacts']
    assert len(entries)==2 and sum(e['current'] for e in entries)==1
    assert len(build_view(f.root,head_id=first['id'])['issue_impacts'])==1


@pytest.mark.parametrize('change',[{'ready':True},{'next_check':''},{'hypotheses':[99]},{'preparation_work':[None]},{'held_work':[None]},{'owner_role':''}])
def test_invalid_assessment_never_mutates_state(tmp_path,change):
    f,row=setup(tmp_path);before=store.read_head(f.root)['id'];row.update(change)
    with pytest.raises(ValueError,match='issue_impact'):
        apply(f,[row])
    assert store.read_head(f.root)['id']==before


def test_forged_issue_reference_is_rejected_atomically(tmp_path):
    f,row=setup(tmp_path);row['issue_ref']['sha256']='0'*64
    before=store.read_head(f.root)['id']
    with pytest.raises(ValueError,match='issue_reference'):
        apply(f,[row])
    assert store.read_head(f.root)['id']==before


def test_issue_status_change_marks_previous_work_proposal_outdated(tmp_path):
    f,row=setup(tmp_path);apply(f,[row]);f.head=store.read_head(f.root)
    issue_id=row['issue_ref']['artifact_id']
    event={**f.envelope('author'),'issue_id':issue_id,'from_status':'open','to_status':'deferred',
           'actor_assignment_id':f.author['id'],'rationale':'Owner explicitly defers this issue',
           'verification_refs':[],'successor_ids':[]}
    f.apply('issue.event',{'issue':None,'event':event})
    view=build_view(f.root)
    assert view['issue_impacts'][0]['current'] is False
    assert view['issues'][0]['status']=='deferred'


def test_current_proposal_uses_commit_order_not_uuid_sort_order(tmp_path):
    f,row=setup(tmp_path)
    for number in range(8):
        row['next_check']=f'확인 절차 {number}'
        apply(f,[row])
        current=[e for e in build_view(f.root)['issue_impacts'] if e['current']]
        assert len(current)==1
        assert current[0]['record']['next_check']==row['next_check']
