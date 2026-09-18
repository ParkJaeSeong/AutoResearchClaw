import pytest
from researchclaw.core.research_graph import commands,store
from researchclaw.codex.service_work_binding import WorkBinding


def prepare(root):
    commands.init_project(root,topic='test',content_origin='synthetic')
    commands.apply_command(root,operation='episode.start',payload=dict(id='w',stage='검토',title='검토',purpose='근거 확인',depends_on=[],return_to=None,return_reason=None,review_required=False),expected_head=store.read_head(root)['id'],command_id='start')
    commands.apply_command(root,operation='work.execution.policy',payload=dict(milestone='M1',status='active',reason='synthetic test'),expected_head=store.read_head(root)['id'],command_id='policy')
    commands.apply_command(root,operation='work.execution.assign',payload=dict(work_id='w',role_id='domain',round_id='initial',input_revision='v1',milestone='M1',active=True),expected_head=store.read_head(root)['id'],command_id='assign')
    return WorkBinding(root,dict(work_id='w',role_id='domain',round_id='initial',input_revision='v1'),{'question':'test'},{})


def test_context_reads_actual_work_and_commit_is_idempotent(tmp_path):
    binding=prepare(tmp_path);ctx=binding.read()
    assert ctx['active'] is True
    result={'review':{'answer':{'rationale':'review','recommendation':None}}}
    first=binding.publish('delivery1',ctx,result)
    assert binding.publish('delivery1',ctx,result)==first
    notes=store.read_head(tmp_path)['state']['work_episodes']['w']['notes']
    assert len(notes)==1
    assert 'review' in notes[0]['text']


def test_finished_work_is_inactive_and_old_publish_rejected(tmp_path):
    binding=prepare(tmp_path);ctx=binding.read()
    commands.apply_command(tmp_path,operation='episode.conclude',payload=dict(id='w',execution_status='finished',judgment='done',remaining='none',next_action='none',next_reason='done'),expected_head=ctx['graph_head'],command_id='end')
    assert binding.read()['active'] is False
    with pytest.raises(ValueError,match='head_conflict'):
        binding.publish('delivery1',ctx,{'review':{}})


def test_nonexistent_work_cannot_be_marked_active(tmp_path):
    binding=prepare(tmp_path);binding.recipient['work_id']='missing'
    assert binding.read()['active'] is False


def test_worker_publishes_before_ack_and_replay_does_not_call_model(tmp_path):
    from researchclaw.codex.service_inbox import ServiceInbox
    from researchclaw.codex.service_review_worker import run_delivery
    binding=prepare(tmp_path)
    inbox=ServiceInbox(tmp_path,store.read_head(tmp_path)['state']['project_id'])
    packet={'answer_state':'stored'}
    delivery=inbox.put('request','answer',store._hash(store._canonical(packet)),binding.recipient,packet)
    calls=[]
    def reviewer(*args):
        calls.append(1)
        return {'answer':{'rationale':'review','recommendation':None}}
    result=run_delivery(inbox,delivery['id'],binding.read,reviewer,publish=binding.publish)
    assert result['state']=='review_complete'
    assert inbox.pending()==[]
    assert len(store.read_head(tmp_path)['state']['work_episodes']['w']['notes'])==1
    assert run_delivery(inbox,delivery['id'],binding.read,reviewer,publish=binding.publish)==result
    assert len(calls)==1


def test_policy_stop_and_assignment_change_disable_binding(tmp_path):
    binding=prepare(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.assign',payload=dict(work_id='w',role_id='critical',round_id='initial',input_revision='v2',milestone='M1',active=True),expected_head=store.read_head(tmp_path)['id'],command_id='reassign')
    assert binding.read()['active'] is False
    binding.recipient.update(role_id='critical',input_revision='v2')
    assert binding.read()['active'] is True
    commands.apply_command(tmp_path,operation='work.execution.policy',payload=dict(milestone='M1',status='stopped',reason='user stop'),expected_head=store.read_head(tmp_path)['id'],command_id='stop')
    assert binding.read()['active'] is False
