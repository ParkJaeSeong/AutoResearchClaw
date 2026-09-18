import json
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.codex.execution_review_runner import run_review, resume_review


def setup(root):
    head=commands.init_project(root,topic='Review fixture',content_origin='synthetic')
    contract=dict(version=1,step_id='evidence_review',purpose_kind='research',purpose='자료 사용 범위 검토',milestone='M1',required_inputs=['source'],roles=['domain','methodology','critical','coordinator'],output_schema='evidence_review_v1',acceptance_checks=['claims','evidence','review'],dependencies=[],allowed_successors=[])
    packet={'sources':[{'evidence_ref':'source-1','text':'Synthetic observation','location':'p.1'}],'metadata':{'content_origin':'synthetic'}}
    commands.apply_command(root,operation='execution.begin',expected_head=head['id'],command_id='begin',payload=dict(work_id='w',attempt_id='a1',generation=1,contract=contract,input=packet,assignment={'roles':contract['roles']}))


def answer(role):
    if role!='coordinator':return dict(rationale='합성 의견',recommendation='limited')
    return dict(claims=[dict(text='합성 관측',evidence_refs=['source-1'],scope='합성 검증')],unresolved=[],recommendation='limited',rationale='사용 범위를 한정합니다.')


def test_progress_barrier_and_terminal_replay(tmp_path):
    setup(tmp_path);calls=[]
    def review(role,phase,packet,materials,run):
        from researchclaw.core.research_graph.execution_view import public_execution
        rows=public_execution(store.read_head(tmp_path))
        assert rows
        if phase=='initial':assert not packet.get('disclosed_initials')
        if phase=='response':assert len(packet['disclosed_initials'])==3
        calls.append((role,phase))
        return {'answer':answer(role),'host_id':'fixture','model_id':'fixture'}
    result=run_review(tmp_path,'w',review)
    assert result['status']=='accepted'
    assert resume_review(tmp_path,'w',review)['status']=='accepted'
    assert len(calls)==10


def test_ambiguous_attempt_is_not_reexecuted(tmp_path):
    setup(tmp_path);calls=[]
    def fail(*args):calls.append(1);raise RuntimeError('simulated process interruption')
    with pytest.raises(RuntimeError):run_review(tmp_path,'w',fail)
    with pytest.raises(ValueError,match='inspection'):resume_review(tmp_path,'w',fail)
    assert len(calls)==1


def test_saved_response_can_be_republished(tmp_path,monkeypatch):
    import researchclaw.codex.execution_review_runner as worker
    setup(tmp_path);calls=[];apply=worker._emit
    def review(role,phase,*args):calls.append((role,phase));return {'answer':answer(role)}
    def fail(root,identity,kind,role,phase,**extra):
        if kind=='role_submitted':raise OSError('disk publication interrupted')
        return apply(root,identity,kind,role,phase,**extra)
    monkeypatch.setattr(worker,'_emit',fail)
    with pytest.raises(OSError):run_review(tmp_path,'w',review)
    monkeypatch.setattr(worker,'_emit',apply)
    assert resume_review(tmp_path,'w',review)['status']=='accepted'
    assert len(calls)==10


def test_stop_during_model_preserves_result_without_adopting(tmp_path):
    setup(tmp_path);calls=[]
    def review(role,phase,*args):
        calls.append(1)
        commands.apply_command(tmp_path,operation='work.execution.policy',expected_head=store.read_head(tmp_path)['id'],command_id='stop',payload={'milestone':'M1','status':'stopped','reason':'fixture stop'})
        return {'answer':answer(role)}
    with pytest.raises(ValueError):run_review(tmp_path,'w',review)
    assert len(calls)==1
    assert list((tmp_path/'.execution-runs').rglob('result.json'))


def test_fresh_process_resumes_cached_result_without_model_reexecution(tmp_path,monkeypatch):
    import subprocess,sys
    import researchclaw.codex.execution_review_runner as worker
    setup(tmp_path);emit=worker._emit
    def interrupt(root,identity,kind,role,phase,**extra):
        if kind=='role_submitted':raise OSError('interruption after result saved')
        return emit(root,identity,kind,role,phase,**extra)
    monkeypatch.setattr(worker,'_emit',interrupt)
    with pytest.raises(OSError):run_review(tmp_path,'w',lambda role,*args:{'answer':answer(role)})
    code='''
import json,sys
from pathlib import Path
from researchclaw.codex.execution_review_runner import resume_review
from tests.codex_native.test_execution_review_runner import answer
calls=[]
def reviewer(role,phase,*args):
    calls.append([role,phase]);return {'answer':answer(role)}
result=resume_review(Path(sys.argv[1]),'w',reviewer)
print(json.dumps({'result':result,'calls':calls}))
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,check=True)
    value=json.loads(child.stdout)
    assert value['result']['status']=='accepted'
    assert len(value['calls'])==9
    assert ['domain','initial'] not in value['calls']
