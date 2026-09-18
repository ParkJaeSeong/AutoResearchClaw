import base64
import hashlib
import json
import pytest
from researchclaw.codex.document_handoff import HandoffJournal, _json
from researchclaw.codex.import_review import ImportReviewQueue


def digest(v):
    return hashlib.sha256(_json(v).encode()).hexdigest()


@pytest.fixture
def setup(tmp_path):
    j=HandoffJournal(tmp_path/'journal.db','project','atlas','pilot')
    data=b'---\ntitle: paper\n---\nEvidence with limits.'
    record={'import_id':'imp','page_refs':[{'page_id':'page','sha256':hashlib.sha256(data).hexdigest()}], 'read_scope':'body only','source_refs':[],'unresolved':['figure unread']}
    event={'event_id':'ev','import_id':'imp','atlas_instance_id':'atlas','outcome':'partial','result_ref':{'import_id':'imp','sha256':digest(record)}}
    with j._db() as db:
        db.execute('INSERT INTO handoffs VALUES (?,?,?)',('convert.jats','key',_json({'atlas_receipt':{'import_id':'imp'},'atlas_payload':{'pilot_project_id':'project'}})))
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',('ev','imp',1,_json(event),_json({'result':{'record':record,'sha256':digest(record)}}),1))
    return j,data


def context(revision='q1'):
    return dict(question_revision=revision,question='What evidence supports the question?',purpose='individual evidence review',policy_revision='v1')


class Client:
    def __init__(self,data,instance='atlas',error=False):self.data=data;self.instance=instance;self.error=error;self.calls=0
    def identity(self,expected):
        if expected!=self.instance:raise ValueError('atlas_instance_mismatch')
    def request(self,*args,**kwargs):
        self.calls+=1
        if self.error:raise ValueError('changed_page')
        h=hashlib.sha256(self.data).hexdigest()
        return {'contract_version':'pilot-atlas/1.0','atlas_instance_id':self.instance,'id':'page','raw':{'encoding':'base64','size_bytes':len(self.data),'sha256':h,'content_base64':base64.b64encode(self.data).decode()}}


def test_reconcile_acked_and_new_question(setup):
    j,_=setup;q=ImportReviewQueue(j)
    first=q.reconcile(context());assert len(first)==1
    assert q.reconcile(context())[0]['id']==first[0]['id']
    assert len(q.reconcile(context('q2')))==1
    with pytest.raises(ValueError,match='context_conflict'):q.reconcile(dict(context(),question='changed without revision'))


def test_freeze_and_restart(setup):
    j,data=setup;q=ImportReviewQueue(j);t=q.reconcile(context())[0];client=Client(data)
    assert q.prepare(t['id'],client)['status']=='input_ready'
    assert ImportReviewQueue(j).prepare(t['id'],client)['status']=='input_ready'
    assert client.calls==1


@pytest.mark.parametrize('client', [Client(b'x',instance='other'),Client(b'x',error=True),Client(b'wrong bytes')])
def test_wrong_instance_changed_page_or_hash_never_ready(setup,client):
    j,_=setup;q=ImportReviewQueue(j);t=q.reconcile(context())[0]
    with pytest.raises(ValueError):q.prepare(t['id'],client)
    assert q.get(t['id'])['status']=='awaiting_input'


def test_failed_result_routes_to_recovery(setup):
    j,_=setup
    with j._db() as db:
        e=json.loads(db.execute('select body from events').fetchone()[0]);e['outcome']='failed';db.execute('update events set body=?',(_json(e),))
    q=ImportReviewQueue(j);t=q.reconcile(context())[0];assert t['status']=='needs_recovery'
    with pytest.raises(ValueError):q.prepare(t['id'],Client(b'x'))


def test_tampered_result_rejected(setup):
    j,_=setup
    with j._db() as db:
        p=json.loads(db.execute('select processed from events').fetchone()[0]);p['result']['record']['read_scope']='tampered';db.execute('update events set processed=?',(_json(p),))
    with pytest.raises(ValueError,match='result_mismatch'):ImportReviewQueue(j).reconcile(context())


def test_corrupt_preserved_page_is_not_reused(setup):
    j,data=setup;q=ImportReviewQueue(j);t=q.reconcile(context())[0];q.prepare(t['id'],Client(data))
    with j._db() as db:db.execute('update import_review_blobs set raw=?',(b'corrupt',))
    with pytest.raises(ValueError,match='blob_corrupt'):q.prepare(t['id'],Client(data))


def test_loader_rejects_wrong_project_before_queue_creation(setup,monkeypatch):
    from researchclaw.codex.import_review import load_queue
    from researchclaw.core.research_graph import store
    import shutil
    j,_=setup;root=j.path.parent/'project';(root/'.document-handoff').mkdir(parents=True)
    shutil.copyfile(j.path,root/'.document-handoff/journal.sqlite3')
    monkeypatch.setattr(store,'read_head',lambda root:{'state':{'project_id':'different'}})
    with pytest.raises(ValueError,match='project_mismatch'):load_queue(root)


def test_completed_review_binding_and_no_overwrite(setup):
    j,data=setup;q=ImportReviewQueue(j);t=q.reconcile(context())[0];t=q.prepare(t['id'],Client(data))
    result={'stage':'review_complete','task_id':t['id'],'packet_sha256':t['packet_sha256'],'research_adoption':False,'rounds':{},'coordinator':{}}
    with pytest.raises(ValueError):q.complete(t['id'],dict(result,task_id='other'))
    q.complete(t['id'],result)
    assert ImportReviewQueue(j).completed(t['id'])==result
    with pytest.raises(ValueError):q.complete(t['id'],dict(result,extra='changed'))
