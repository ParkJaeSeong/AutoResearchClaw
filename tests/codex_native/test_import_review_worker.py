import pytest
from researchclaw.codex.import_review_worker import dispatch

class Queue:
    def execution(self,k,status):self.execution_status=status
    def reconcile(self,c):return [{'id':'a'},{'id':'b'}]
    def get(self,k):return {'id':k,'status':'awaiting_input'}
    def completed(self,k):return {'stage':'review_complete'} if k=='a' else None
    def prepare(self,k,c):return {'id':k,'status':'input_ready'}
    def complete(self,k,r):self.saved=(k,r)

def test_completed_task_skipped_and_other_runs(tmp_path):
    q=Queue();calls=[]
    def run(q,k,p,r):calls.append(k);return {'stage':'review_complete'}
    result=dispatch(q,{},None,None,tmp_path,run)
    assert calls==['b'] and q.saved[0]=='b'
    assert result['errors']==[]

def test_failure_keeps_other_results(tmp_path):
    q=Queue()
    def fail(*a):raise ValueError('changed_page')
    q.prepare=fail
    result=dispatch(q,{},None,None,tmp_path,lambda *a:pytest.fail('model called'))
    assert result['errors']==[{'task_id':'b','code':'changed_page'}]


def test_changed_question_prevents_observation(tmp_path,monkeypatch):
    from researchclaw.codex import import_review_worker as w
    (tmp_path/'question.md').write_text('new')
    monkeypatch.setattr(w,'load_queue',lambda root:pytest.fail('must reject before dispatch'))
    with pytest.raises(ValueError,match='question_changed'):
        w.tick(tmp_path,{'question_source':'question.md','question_revision':'old'},None,None,None,None)


def test_project_lock_blocks_second_worker(tmp_path,monkeypatch):
    import fcntl,hashlib
    from researchclaw.codex import import_review_worker as w
    (tmp_path/'question.md').write_text('q')
    context={'question_source':'question.md','question_revision':hashlib.sha256(b'q').hexdigest(),'question':'q'}
    runs=tmp_path/'.document-handoff/review-runs';runs.mkdir(parents=True)
    monkeypatch.setattr(w,'load_queue',lambda root:object())
    monkeypatch.setattr(w,'configured_adapter',lambda *a:pytest.fail('observer should not run'))
    with (runs/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='worker_busy'):w.tick(tmp_path,context,None,None,None,None)


def test_saved_review_is_returned_without_model_reexecution(tmp_path):
    q=Queue();published=[]
    dispatch(q,{},None,None,tmp_path,lambda *a:{'stage':'review_complete'},publish=lambda k,r:published.append(k))
    assert published==['a','b']


def test_return_failure_preserves_saved_review(tmp_path):
    q=Queue()
    def publish(*args):raise ValueError('head_conflict')
    result=dispatch(q,{},None,None,tmp_path,lambda *a:{'stage':'review_complete'},publish=publish)
    assert q.saved[0]=='b'
    assert len(result['errors'])==2


def test_publish_import_review_replays_without_duplicate_notes(tmp_path):
    from researchclaw.codex.import_review_worker import publish_review
    from researchclaw.core.research_graph import commands,store
    from tests.codex_native.test_service_work_binding import prepare
    prepare(tmp_path)
    task={'request':{'work_ref':'w'},'context':{'work_id':'w'},'result':{'sha256':'sourcehash'}}
    result={'rounds':{'initial':[{'role':'domain','answer':{'rationale':'CF/PP opinion'}}]},'coordinator':{'answer':{'rationale':'Next: compare recycling routes'}}}
    publish_review(tmp_path,'task',task,result)
    publish_review(tmp_path,'task',task,result)
    ep=store.read_head(tmp_path)['state']['work_episodes']['w']
    assert len(ep['notes'])==2 and ep['conclusion'] is None
    assert 'CF/PP opinion' in ep['notes'][0]['text']


def test_saved_return_recovers_execution_status(tmp_path):
    q=Queue();q.reconcile=lambda c:[{'id':'a'}]
    dispatch(q,{},None,None,tmp_path,publish=lambda *args:None)
    assert q.execution_status=='review_complete'


def test_closed_work_rejects_return_without_changing_graph(tmp_path):
    from researchclaw.codex.import_review_worker import publish_review
    from researchclaw.core.research_graph import commands,store
    from tests.codex_native.test_service_work_binding import prepare
    prepare(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.policy',payload=dict(milestone='M1',status='stopped',reason='user pause'),expected_head=store.read_head(tmp_path)['id'],command_id='stop')
    before=store.read_head(tmp_path)['id']
    with pytest.raises(ValueError,match='review_work_not_active'):
        publish_review(tmp_path,'task',{'context':{'work_id':'w'},'request':{'work_ref':'w'}},{})
    assert store.read_head(tmp_path)['id']==before
