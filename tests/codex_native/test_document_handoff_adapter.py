import hashlib
import json
import pytest
from researchclaw.codex.document_handoff import HandoffJournal, HandoffConflict
from researchclaw.codex.document_handoff_adapter import HandoffAdapter, canonical_hash, atlas_key

V='pilot-documents-atlas/1.0'

class Remote:
    def __init__(self, kind):
        self.kind=kind;self.calls=[];self.capable=True;self.lose=False;self.acked=False
        self.receipt=None;self.record=None;self.phase='organizing';self.updated=1
        self.result=None;self.bad_hash=False
    def request(self, method, path, payload=None, params=None):
        self.calls.append((method,path,payload,params))
        if path=='/api/integration/info':return dict(contract_version=V,instance_id='D',capabilities=['document_handoff_v1'] if self.capable else [])
        if path=='/api/info':return dict(atlas_instance_id='A',import_contract_version=V,capabilities=['documents_import_v1'] if self.capable else [])
        if '/receipts/' in path:return self.receipt
        if path=='/api/tasks/t':return dict(id='t',instance_id='D',contract_version=V,file_hash='a'*64,input_fingerprint='b'*64)
        if path=='/api/document-imports':
            if self.record is None:
                self.record=dict(import_id='i',atlas_instance_id='A',consumer_id='pilot',request_key=payload['request_key'],payload=payload,
                    receipt_ref=dict(atlas_instance_id='A',operation='documents.import',request_key=payload['request_key'],request_sha256=canonical_hash({k:v for k,v in payload.items() if k!='request_key'}),import_id='i'))
            if self.lose:self.lose=False;raise OSError('response lost')
            return self.envelope()
        if path=='/api/document-imports/i':return self.envelope()
        if path=='/api/events':
            events=[]
            if self.result:
                events=[dict(atlas_instance_id='A',consumer_id='pilot',event_id='e',sequence=1,import_id='i',request_key=self.record['request_key'],phase='terminal',outcome='partial',result_ref=dict(import_id='i',sha256=canonical_hash(self.result)),acknowledged=self.acked)]
            return dict(ok=True,contract_version=V,atlas_instance_id='A',events=events,next_cursor=None)
        if path=='/api/events/ack':
            self.acked=True
            if self.lose:self.lose=False;raise OSError('ack lost')
            return dict(ok=True,contract_version=V,atlas_instance_id='A',acknowledged=payload['event_ids'])
        raise AssertionError(path)
    def envelope(self):
        result={'record':self.result,'sha256':'f'*64 if self.bad_hash else canonical_hash(self.result)} if self.result else None
        return dict(ok=True,contract_version=V,atlas_instance_id='A',**{'import':dict(self.record,phase=self.phase,outcome='partial' if self.result else None,updated_at=self.updated,result=result)})


def setup(tmp_path):
    j=HandoffJournal(tmp_path/'journal.sqlite3','P','A','pilot');d=Remote('documents');a=Remote('atlas')
    d.receipt=dict(contract_version=V,instance_id='D',operation='convert.jats',request_key='k',request_sha256='c'*64,receipt_id='r',task_id='t',submitted_by_consumer_id='pilot',retrieval_consumer_id='atlas',config_revision='cfg',result_ref=None,acknowledged_at=None)
    j.enqueue('convert.jats','k',{'config_revision':'cfg','retrieval_consumer_id':'atlas'},dict(documents_service_ref={'alias':'documents','instance_id':'D'},source={'sha256':'a'*64,'mime_type':'application/xml','filename':'paper.xml'},atlas_project_id='AP',work_ref='w',question_ref=None,bibliography={'title':'Paper'},source_url=None,purpose='compare',requested_scope='methods',requested_indexes=['bm25'],partial_policy='available_then_partial',original_ref={'role':'source_original'}))
    return j,d,a,HandoffAdapter(j,d,a)


def test_recovery_pins_supplier_package_and_separate_key(tmp_path):
    j,d,a,s=setup(tmp_path);a.lose=True
    with pytest.raises(OSError):s.advance()
    assert j.pending()[0]['destination']=='atlas'
    s.advance()
    assert j.pending()==[]
    assert a.record['payload']['package_fingerprint']=='b'*64
    assert a.record['request_key']!= 'k'
    assert atlas_key('P','convert.jats','k')!=atlas_key('P','convert.file','k')
    assert sum('/receipts/' in c[1] for c in d.calls)==1
    assert j.rows()[0]['snapshot']['phase']=='organizing'


def test_result_hash_ack_loss_and_mutable_ack_replay(tmp_path):
    j,d,a,s=setup(tmp_path);s.advance()
    a.phase='terminal';a.updated=2
    a.result=dict(import_id='i',documents_result_ref={'instance_id':'D','task_id':'t','result_revision':'r1','manifest_sha256':'d'*64},source_refs=[],extraction_refs=[],page_refs=[],read_scope='methods',unresolved=['missing figure'],index_status={},ingest_job_ref='job')
    a.bad_hash=True
    with pytest.raises(ValueError):s.poll()
    assert not a.acked and not j.pending_acks()
    assert j.rows()[0]['last_error']=='atlas_result_mismatch'
    a.bad_hash=False;a.lose=True
    with pytest.raises(OSError):s.poll()
    assert j.pending_acks()==['e']
    s.poll()
    assert not j.pending_acks()
    assert j.pending_events()==[]


def test_capability_absent_blocks_submission(tmp_path):
    j,d,a,s=setup(tmp_path);d.capable=False
    with pytest.raises(ValueError):s.advance()
    assert j.pending()[0]['destination']=='documents'
    assert not any(c[0]=='POST' for c in a.calls+d.calls)


def test_older_snapshot_does_not_regress_ui(tmp_path):
    j,d,a,s=setup(tmp_path);s.advance();a.updated=0;a.phase='waiting_conversion';s.poll()
    assert j.rows()[0]['snapshot']['phase']=='organizing'


def test_foreign_events_are_not_acked(tmp_path):
    j,d,a,s=setup(tmp_path);s.advance()
    original=a.request
    def wrapped(method,path,payload=None,params=None):
        if path=='/api/events':
            return dict(ok=True,contract_version=V,atlas_instance_id='A',events=[dict(import_id='foreign',event_id='foreign')],next_cursor=None)
        return original(method,path,payload,params)
    a.request=wrapped;s.poll()
    assert not a.acked


def test_snapshot_projects_intermediate_state_without_adoption(tmp_path):
    from researchclaw.codex.document_handoff_view import build_handoff_view
    root=tmp_path/'project';root.mkdir()
    j,d,a,s=setup(root/'.document-handoff');s.advance()
    item=build_handoff_view(root,'P')['items'][0]
    assert item['status']=='organizing'
    assert item['pilot_review']=='unrecorded'


def test_successful_result_visible_only_after_verified_processing(tmp_path):
    from researchclaw.codex.document_handoff_view import build_handoff_view
    root=tmp_path/'project';root.mkdir();j,d,a,s=setup(root/'.document-handoff');s.advance()
    assert build_handoff_view(root,'P')['items'][0]['result_received'] is False
    a.phase='terminal';a.updated=2
    a.result=dict(import_id='i',documents_result_ref={'instance_id':'D','task_id':'t','result_revision':'r1','manifest_sha256':'d'*64},source_refs=[],extraction_refs=[],page_refs=[],read_scope='methods only',unresolved=['figure missing'],index_status={},ingest_job_ref='job')
    s.poll()
    item=build_handoff_view(root,'P')['items'][0]
    assert item['result_received'] is True
    assert item['read_scope']=='methods only'
    assert item['unresolved']==['figure missing']
    assert item['pilot_review']=='unrecorded'


def test_missing_package_preserves_receipt_and_marks_attention(tmp_path):
    from researchclaw.codex.document_handoff_view import build_handoff_view
    root=tmp_path/'project';root.mkdir();j,d,a,s=setup(root/'.document-handoff')
    original=d.request
    def missing(method,path,payload=None,params=None):
        result=original(method,path,payload,params)
        if path=='/api/tasks/t':result.pop('input_fingerprint')
        return result
    d.request=missing
    with pytest.raises(ValueError,match='package_fingerprint_missing'):s.advance()
    assert j.pending()[0]['destination']=='atlas'
    assert build_handoff_view(root,'P')['items'][0]['status']=='needs_attention'
    assert not a.record
    d.request=original;s.advance()
    assert build_handoff_view(root,'P')['items'][0]['status']=='organizing'


def test_empty_event_tail_cursor_is_not_an_error(tmp_path):
    j,d,a,s=setup(tmp_path);s.advance();original=a.request
    def tail(method,path,payload=None,params=None):
        if path=='/api/events':return dict(ok=True,contract_version=V,atlas_instance_id='A',events=[],next_cursor='tail-0')
        return original(method,path,payload,params)
    a.request=tail;s.poll()
    assert not j.pending_events()


def test_event_tail_position_survives_observer_restart(tmp_path):
    j,d,a,s=setup(tmp_path);s.advance();original=a.request;seen=[]
    def tail(method,path,payload=None,params=None):
        if path=='/api/events':
            seen.append(params.get('cursor'))
            return dict(ok=True,contract_version=V,atlas_instance_id='A',events=[],next_cursor='position-0')
        return original(method,path,payload,params)
    a.request=tail;s.poll()
    reopened=HandoffJournal(j.path,'P','A','pilot');HandoffAdapter(reopened,d,a).poll()
    assert seen==[None,'position-0']
