import pytest
from researchclaw.core.research_graph import commands, store
from tests.codex_native.research_graph.test_execution_contracts import contract, packet, result


def apply(root, op, payload, cid=None):
    snap=commands.read_policy_snapshot(root)
    return commands.apply_command(root,operation='execution.'+op,payload=payload,expected_head=snap['id'],command_id=cid or str(len(snap['events']))+'-'+op+'-'+str(snap['id']))


def begin(root, sources=None):
    commands.init_project(root,topic='lifecycle fixture',content_origin='synthetic')
    return apply(root,'begin',dict(work_id='review',attempt_id='a1',generation=1,contract=contract(),input=packet() if sources is None else sources,assignment={'roles':contract()['roles']}))


def record(root, role, phase, kind='role_submitted', output=None, gen=1, attempt='a1'):
    return apply(root,'record',dict(work_id='review',attempt_id=attempt,generation=gen,kind=kind,actor=role,payload={'phase':phase,**({'result':output or result()} if kind=='role_submitted' else {})}))


def rounds(root):
    for phase in ['initial','response','final']:
        for role in ['domain','methodology','critical']:
            record(root,role,phase,'role_started');record(root,role,phase)
    record(root,'coordinator','final','role_started');record(root,'coordinator','final')


def test_lifecycle_freezes_objects_and_requires_reviews(tmp_path):
    snap=begin(tmp_path)
    assert snap['state']['execution_work']['review']['status']=='running'
    with pytest.raises(ValueError,match='phase_barrier'):record(tmp_path,'domain','response','role_started')
    snap=apply(tmp_path,'finish',dict(work_id='review',attempt_id='a1',generation=1,result=result()))
    assert snap['state']['execution_work']['review']['status']=='needs_work'


def test_acceptance_policy_and_revise(tmp_path):
    begin(tmp_path);rounds(tmp_path)
    snap=apply(tmp_path,'finish',dict(work_id='review',attempt_id='a1',generation=1,result=result()))
    assert snap['state']['execution_work']['review']['status']=='accepted'
    with pytest.raises(ValueError,match='execution_milestone_gate_required'):
        commands.apply_command(tmp_path,operation='work.execution.policy',payload={'milestone':'M1','status':'completed','reason':'done'},expected_head=snap['id'],command_id='complete')
    apply(tmp_path,'revise',dict(work_id='review',previous_attempt_id='a1',attempt_id='a2',generation=2,input=packet(),reason='new source'))
    with pytest.raises(ValueError,match='stale'):record(tmp_path,'domain','initial','role_started')
    current=commands.read_policy_snapshot(tmp_path)['state']['execution_work']['review']
    assert current['attempts']['a1']['status']=='accepted'
    assert current['attempts']['a2']['status']=='running'


def test_missing_source_and_idempotency(tmp_path):
    snap=begin(tmp_path,{'sources':[]})
    assert snap['state']['execution_work']['review']['status']=='blocked'
    payload=dict(work_id='review',previous_attempt_id='a1',attempt_id='a2',generation=2,input=packet(),reason='source added')
    first=apply(tmp_path,'revise',payload,'revise')
    second=apply(tmp_path,'revise',payload,'revise')
    assert first['id']==second['id']
    with pytest.raises(ValueError,match='command_conflict'):apply(tmp_path,'revise',{**payload,'reason':'changed'},'revise')


def test_policy_change_preserves_result_without_acceptance(tmp_path):
    begin(tmp_path);rounds(tmp_path)
    snap=commands.read_policy_snapshot(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.policy',payload={'milestone':'M1','status':'stopped','reason':'stop'},expected_head=snap['id'],command_id='stop')
    snap=apply(tmp_path,'finish',dict(work_id='review',attempt_id='a1',generation=1,result=result()))
    attempt=snap['state']['execution_work']['review']['attempts']['a1']
    assert attempt['status']=='needs_work' and attempt['result']==result()
    assert attempt['output_report']['checks'][0]['reason']=='policy_stale'


def test_unknown_submission_field_cannot_escape_schema(tmp_path):
    begin(tmp_path);record(tmp_path,'domain','initial','role_started')
    with pytest.raises(ValueError,match='submission_invalid'):
        record(tmp_path,'domain','initial',output={'rationale':'ok','recommendation':'use','secret':'token'})


def test_stop_blocks_new_role_intents(tmp_path):
    snap=begin(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.policy',payload={'milestone':'M1','status':'stopped','reason':'stop'},expected_head=snap['id'],command_id='stop')
    with pytest.raises(ValueError,match='policy_stale'):record(tmp_path,'domain','initial','role_started')


def test_stop_blocks_late_submission_atomically(tmp_path):
    begin(tmp_path);record(tmp_path,'domain','initial','role_started')
    snap=commands.read_policy_snapshot(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.policy',payload={'milestone':'M1','status':'stopped','reason':'stop'},expected_head=snap['id'],command_id='stop')
    head=commands.read_policy_snapshot(tmp_path)['id']
    with pytest.raises(ValueError,match='policy_stale'):record(tmp_path,'domain','initial')
    assert commands.read_policy_snapshot(tmp_path)['id']==head
