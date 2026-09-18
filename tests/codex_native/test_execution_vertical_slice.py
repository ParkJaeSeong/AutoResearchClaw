"""Public-command integration; no external submissions or seeded completion."""
from copy import deepcopy
import pytest
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.execution_view import public_execution
from researchclaw.codex.execution_review_runner import run_review, resume_review
from tests.codex_native.test_execution_review_runner import setup, answer


def apply(root,operation,key,payload):
    return commands.apply_command(root,operation=operation,command_id=key,
        expected_head=store.read_head(root)['id'],payload=payload)


def test_failed_check_rework_restart_and_no_milestone_completion(tmp_path):
    setup(tmp_path);calls=[]
    def reviewer(role,phase,packet,materials,run):
        calls.append((role,phase))
        result=answer(role)
        if role=='coordinator':result['claims'][0]['evidence_refs']=['missing-source']
        return {'answer':result}
    assert run_review(tmp_path,'w',reviewer)['status']=='needs_work'
    first=store.read_head(tmp_path);old=deepcopy(first['state']['execution_work']['w']['attempts']['a1'])
    apply(tmp_path,'execution.revise','revise',dict(work_id='w',previous_attempt_id='a1',attempt_id='a2',generation=2,reason='근거 위치 보완',input=old['input']))
    result=resume_review(tmp_path,'w',lambda role,*args:{'answer':answer(role)})
    assert result['status']=='accepted'
    current=store.read_head(tmp_path)
    assert current['state']['execution_work']['w']['attempts']['a1']==old
    assert len(public_execution(current)[0]['attempts'])==2
    assert public_execution(first)[0]['status']=='needs_work'
    assert current['state'].get('work_execution_policy',{}).get('status')!='completed'
    with pytest.raises(ValueError,match='milestone_gate_required'):
        apply(tmp_path,'work.execution.policy','bypass',dict(milestone='M1',status='completed',reason='model said done'))


def test_missing_source_blocks_start_without_model(tmp_path):
    setup(tmp_path)
    apply(tmp_path,'execution.revise','empty',dict(work_id='w',previous_attempt_id='a1',attempt_id='a2',generation=2,reason='입력 교체',input={'sources':[]}))
    assert run_review(tmp_path,'w',lambda *a:pytest.fail('model must not run'))['status']=='blocked'
    assert not list((tmp_path/'.execution-runs').glob('*'))
