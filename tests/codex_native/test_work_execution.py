import pytest
from researchclaw.core.research_graph import commands,store


def apply(root,op,payload,key):
    return commands.apply_command(root,operation=op,payload=payload,command_id=key,expected_head=store.read_head(root)['id'])


def setup(root):
    commands.init_project(root,topic='test',content_origin='synthetic')
    apply(root,'episode.start',dict(id='w',stage='review',title='review',purpose='review',depends_on=[],return_to=None,return_reason=None,review_required=False),'start')


def test_execution_policy_and_binding_are_explicit(tmp_path):
    setup(tmp_path)
    apply(tmp_path,'work.execution.policy',dict(milestone='M1',status='active',reason='test approval'),'policy')
    result=apply(tmp_path,'work.execution.assign',dict(work_id='w',role_id='domain',round_id='initial',input_revision='v1',milestone='M1',active=True),'assign')
    assert result['state']['work_execution_assignments']['w']['role_id']=='domain'
    apply(tmp_path,'work.execution.policy',dict(milestone='M1',status='stopped',reason='user stop'),'stop')
    with pytest.raises(ValueError,match='execution_not_active'):
        apply(tmp_path,'work.execution.assign',dict(work_id='w',role_id='domain',round_id='final',input_revision='v2',milestone='M1',active=True),'again')


def test_next_milestone_cannot_be_assigned(tmp_path):
    setup(tmp_path)
    apply(tmp_path,'work.execution.policy',dict(milestone='M1',status='active',reason='test'),'policy')
    with pytest.raises(ValueError,match='milestone'):
        apply(tmp_path,'work.execution.assign',dict(work_id='w',role_id='domain',round_id='initial',input_revision='v1',milestone='M2',active=True),'assign')


def test_followup_requires_recorded_review_and_remains_planned(tmp_path):
    setup(tmp_path)
    payload=dict(id='next1',work_id='w',delivery_id='d1',action='ask_atlas',purpose='fill gap',reason='missing evidence')
    with pytest.raises(ValueError,match='review_missing'):
        apply(tmp_path,'work.execution.followup',payload,'next')
    import json
    apply(tmp_path,'episode.note',dict(id='w',kind='output',author='domain',text=json.dumps(dict(delivery_id='d1',review={'answer':{'rationale':'gap'}}))),'note')
    result=apply(tmp_path,'work.execution.followup',payload,'next')
    assert result['state']['service_followups']['next1']['status']=='planned'
    assert len(result['state']['work_episodes'])==1


def ready_followup(root):
    setup(root)
    apply(root,'work.execution.policy',dict(milestone='M1',status='active',reason='approved M1'),'policy')
    import json
    apply(root,'episode.note',dict(id='w',kind='output',author='domain',text=json.dumps(dict(delivery_id='d1',review={'answer':{'rationale':'gap'}}))),'note')
    apply(root,'work.execution.followup',dict(id='next1',work_id='w',delivery_id='d1',action='ask_atlas',purpose='Which conditions remain unknown?',reason='missing evidence'),'plan')


def test_start_followup_is_atomic_and_does_not_duplicate_work(tmp_path):
    ready_followup(tmp_path)
    first=apply(tmp_path,'work.execution.start',{'id':'next1'},'start-next')
    second=apply(tmp_path,'work.execution.start',{'id':'next1'},'retry-next')
    row=second['state']['service_followups']['next1']
    assert row['status']=='started'
    assert row['execution_authorized'] is True
    assert row['target_work_id'] in first['state']['work_episodes']
    assert len(second['state']['work_episodes'])==2


@pytest.mark.parametrize('status',['stopped','completed'])
def test_start_followup_respects_milestone_stop(tmp_path,status):
    ready_followup(tmp_path)
    apply(tmp_path,'work.execution.policy',dict(milestone='M1',status=status,reason='stop'),'stop')
    with pytest.raises(ValueError,match='execution_not_active'):
        apply(tmp_path,'work.execution.start',{'id':'next1'},'start-next')
    assert len(store.read_head(tmp_path)['state']['work_episodes'])==1
