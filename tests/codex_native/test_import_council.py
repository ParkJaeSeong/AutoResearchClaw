import json
import pytest
from researchclaw.codex.import_council import run_import_council


class Queue:
    def __init__(self):self.task={'id':'task','status':'input_ready','packet_sha256':'hash','context':{'question_revision':'q'}}
    def get(self,key):return self.task
    def materials(self,key):return {'question':'q','pages':['actual page']}


def test_independent_first_phase_resume_and_coordinator(tmp_path):
    calls=[]
    def review(role,phase,packet,materials,run):
        calls.append((role,phase))
        if phase=='initial':assert packet['disclosed_initials']==[] and packet['disclosed_responses']==[]
        if phase=='response':assert len(packet['disclosed_initials'])==3
        if phase=='final':assert len(packet['disclosed_responses'])==3
        return {'answer':{'rationale':role+' judgment','recommendation':'ready_with_limits' if phase=='final' else None},'host_id':'test','model_id':'test'}
    q=Queue();first=run_import_council(q,'task',tmp_path,review)
    assert len(calls)==10 and first['stage']=='review_complete'
    assert first['coordinator']['answer']['rationale']=='coordinator judgment'
    assert run_import_council(q,'task',tmp_path,review)==first and len(calls)==10


def test_wrong_input_never_executes(tmp_path):
    q=Queue();q.task['status']='awaiting_input'
    with pytest.raises(ValueError):run_import_council(q,'task',tmp_path,lambda *a:pytest.fail('called'))


def test_project_persona_and_purpose_pass_to_every_review(tmp_path):
    q=Queue();q.task['context'].update(personas={'domain':{'role':'CF/PP','contract':'fiber length'}},milestone_purpose='CF/PP M1',purpose='individual review')
    def review(role,phase,packet,materials,run):
        assert materials['personas']['domain']['role']=='CF/PP'
        assert materials['milestone_purpose']=='CF/PP M1'
        assert materials['review_scope']=='individual review'
        return {'answer':{'rationale':'ok','recommendation':None}}
    run_import_council(q,'task',tmp_path,review)


def test_progress_is_published_before_entire_council_finishes(tmp_path):
    events=[]
    def review(role,phase,packet,materials,run):
        assert any(e['kind']=='role_started' and e['role']==role and e['phase']==phase for e in events)
        if phase=='response':
            assert any(e['kind']=='phase_ready' and e['phase']=='initial' for e in events)
        return {'answer':{'rationale':role,'recommendation':None}}
    run_import_council(Queue(),'task',tmp_path,review,on_event=events.append)
    assert len([e for e in events if e['kind']=='role_submitted'])==10
    assert len([e for e in events if e['kind']=='phase_ready'])==3


def test_callback_failure_preserves_result_for_republication(tmp_path):
    calls=[]
    def review(role,phase,packet,materials,run):
        calls.append((role,phase))
        return {'answer':{'rationale':role,'recommendation':None}}
    def fail(event):
        if event['kind']=='role_submitted':raise ValueError('publication_failed')
    with pytest.raises(ValueError,match='publication_failed'):
        run_import_council(Queue(),'task',tmp_path,review,on_event=fail)
    run_import_council(Queue(),'task',tmp_path,review,on_event=lambda event:None)
    assert len(calls)==10
