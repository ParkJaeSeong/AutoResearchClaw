import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from researchclaw.core.research_graph import commands, store


def test_service_modules_exist():
    from researchclaw.codex.atlas_client import AtlasClient, unpack_raw
    from researchclaw.codex.atlas_session import AtlasSession
    assert callable(AtlasClient) and callable(AtlasSession)


def packed(data):
    return dict(encoding='base64', content_base64=base64.b64encode(data).decode(),
                size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def test_raw_rejects_length_hash_and_encoding():
    from researchclaw.codex.atlas_client import unpack_raw
    value=packed(b'original\r\n')
    assert unpack_raw(value,value['sha256'])==b'original\r\n'
    for field,bad in [('size_bytes',1),('sha256','0'*64),('encoding','utf8')]:
        with pytest.raises(ValueError): unpack_raw(dict(value,**{field:bad}),value['sha256'])


class Atlas:
    instance='instance-A'
    lose=False
    def __init__(self): self.jobs={}; self.posts=0
    def identity(self,expected=None):
        if expected and self.instance!=expected: raise ValueError('atlas_instance_mismatch')
        return dict(atlas_instance_id=self.instance,capabilities=['qa_export_v1','page_raw_v1'])
    def request(self,method,path,payload=None,params=None):
        if path=='/api/projects': return {'projects':[{'id':'P','title':'Polymer'},{'id':'Q','title':'Other'}]}
        if path=='/api/jobs':
            self.posts+=1;key=payload['request_key']
            self.jobs.setdefault(key,dict(id='job-'+key,status='completed',payload=deepcopy(payload),
                atlas_instance_id=self.instance,request_key=key,request_sha256='a'*64,
                receipt_ref=dict(atlas_instance_id=self.instance,operation='jobs.submit',request_key=key,request_sha256='a'*64),detail={}))
            job=self.jobs[key];data=('---\nschema_version: 1\nid: qa-'+key+'\nquestion: '+json.dumps(payload['question'],ensure_ascii=False)+'\nanswer: Evidence answer\nproject: '+payload['project']+'\nconsulted_pages: []\ncandidates: []\n---\n').encode()
            job['detail']['qa_ref']={'qa_id':'qa-'+key,'sha256':packed(data)['sha256']};job['data']=data
            if self.lose:self.lose=False;raise ValueError('atlas_transport_unavailable')
            return dict(ok=True,contract_version='pilot-atlas/1.0',atlas_instance_id=self.instance,job={k:v for k,v in job.items() if k!='data'})
        if path.startswith('/api/jobs/'):
            job=next(v for v in self.jobs.values() if v['id']==path.split('/')[-1]);return dict(ok=True,contract_version='pilot-atlas/1.0',atlas_instance_id=self.instance,job={k:v for k,v in job.items() if k!='data'})
        if path.startswith('/api/qa/'):
            job=next(v for v in self.jobs.values() if v['detail']['qa_ref']['qa_id']==path.split('/')[-1]);return dict(ok=True,contract_version='pilot-atlas/1.0',atlas_instance_id=self.instance,qa_id=job['detail']['qa_ref']['qa_id'],raw=packed(job['data']),lifecycle=None)
        raise AssertionError(path)


def session(tmp_path):
    from researchclaw.codex.atlas_session import AtlasSession
    commands.init_project(tmp_path,topic='Integration test',content_origin='synthetic')
    client=Atlas();return AtlasSession(tmp_path,client),client


def test_lost_response_resume_same_key_and_binding_history(tmp_path):
    from researchclaw.codex.atlas_session import AtlasSession
    s,c=session(tmp_path);s.bind('P','Test');c.lose=True
    with pytest.raises(ValueError):s.ask('k','Question?','q1')
    assert s.status()['requests'][0]['request_key']=='k'
    s.bind('Q','New context')
    s=AtlasSession(tmp_path,c);s.poll('k')
    assert len(c.jobs)==1
    assert c.jobs['k']['payload']['project']=='P'
    with pytest.raises(ValueError,match='conflict'):s.ask('k','Changed?','q1')
    c.instance='instance-B'
    with pytest.raises(ValueError,match='instance'):s.poll('k')


def test_receive_is_idempotent_and_keeps_raw(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    head=store.read_head(tmp_path)['id'];one=s.receive('k',head)
    two=s.receive('k',head)
    assert one['import_result']==two['import_result']
    from researchclaw.core.research_graph.views import build_view
    assert len(build_view(tmp_path)['external_evidence'])==1
    assert s.status()['requests'][0]['received'] is True


def test_unsafe_connection_and_redirect_not_followed(tmp_path):
    from researchclaw.codex.atlas_client import AtlasClient
    p=tmp_path/'connection.json';p.write_text(json.dumps({'url':'https://example.com','token':'secret'}));p.chmod(0o600)
    with pytest.raises(ValueError,match='connection'):AtlasClient(p).identity()
    p.write_text(json.dumps({'url':'http://127.0.0.1:1','token':'secret'}));p.chmod(0o644)
    with pytest.raises(ValueError,match='connection'):AtlasClient(p).identity()


def test_bad_qa_never_imports_and_page_failure_is_preserved(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    head=store.read_head(tmp_path)['id'];request=c.request
    def corrupt(method,path,payload=None,params=None):
        value=request(method,path,payload,params)
        if '/qa/' in path:value['raw']['size_bytes']+=1
        return value
    c.request=corrupt
    with pytest.raises(ValueError):s.receive('k',head)
    assert store.read_head(tmp_path)['id']==head
    c.request=request
    s.receive('k',head)
    assert 'supporting' in s.status()['requests'][0]


def test_source_chunks_must_have_contiguous_offsets(tmp_path):
    from researchclaw.codex.atlas_client import AtlasClient
    c=AtlasClient(tmp_path/'unused')
    data=b'source';value=dict(source_id='s',version=1,sha256=packed(data)['sha256'],size=len(data),offset=1,next_offset=len(data),eof=True,content_base64=packed(data)['content_base64'])
    c.request=lambda *a,**k:value
    with pytest.raises(ValueError,match='source'):c.source('s',1)


def test_service_dispatch_rejects_browser_connection_path(tmp_path,monkeypatch):
    from researchclaw.codex.atlas_http import dispatch_atlas
    commands.init_project(tmp_path,topic='UI',content_origin='synthetic')
    with pytest.raises(ValueError,match='request_invalid'):
        dispatch_atlas(tmp_path,'service-connect',{'connection_file':'/tmp/token'})
    monkeypatch.delenv('PILOT_ATLAS_CONNECTION_FILE',raising=False)
    with pytest.raises(ValueError,match='not_configured'):
        dispatch_atlas(tmp_path,'service-connect',{})


def test_receipt_wrong_operation_and_context_rejected(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    c.jobs['k']['receipt_ref']['operation']='uploads.commit'
    with pytest.raises(ValueError,match='receipt'):s.poll('k')
    c.jobs['k']['receipt_ref']['operation']='jobs.submit'
    c.jobs['k']['payload']['client_context']['question_id']='other'
    with pytest.raises(ValueError,match='reference'):s.poll('k')


def test_import_head_conflict_can_resume_offline_from_saved_original(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    with pytest.raises(ValueError,match='head_conflict'):s.receive('k','0'*64)
    def offline(*a,**kw):raise ValueError('atlas_transport_unavailable')
    c.request=offline;c.identity=offline
    r=s.receive('k',store.read_head(tmp_path)['id'])
    assert r['received'] is True


def test_source_final_chunk_uses_null_next_offset(tmp_path):
    from researchclaw.codex.atlas_client import AtlasClient
    c=AtlasClient(tmp_path/'unused');data=b'whole source'
    c.request=lambda *a,**k:dict(source_id='s',version=1,sha256=packed(data)['sha256'],size=len(data),offset=0,next_offset=None,eof=True,content_base64=packed(data)['content_base64'])
    ref,raw=c.source('s',1)
    assert raw==data and ref['sha256']==packed(data)['sha256']


def test_supporting_retry_preserves_attempt_and_never_reimports(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    s.receive('k',store.read_head(tmp_path)['id']);head=store.read_head(tmp_path)['id']
    r=s.refresh_supporting('k');assert len(r['supporting_history'])==1
    assert store.read_head(tmp_path)['id']==head


def test_response_envelope_instance_is_checked(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1');request=c.request
    def wrong(*a,**kw):return dict(request(*a,**kw),atlas_instance_id='other')
    c.request=wrong
    with pytest.raises(ValueError,match='instance'):s.poll('k')


def test_followup_transmits_context_and_freezes_it_before_submission(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Full question?','q1')
    s.ask('next','Why?','q2',previous='k')
    assert 'Full question?' in c.jobs['next']['payload']['question']
    assert 'Why?' in c.jobs['next']['payload']['question']
    assert s.status()['requests'][-1]['question']=='Why?'


def test_http_errors_preserve_safe_limits_without_server_secrets(tmp_path):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    from researchclaw.codex.atlas_client import AtlasClient,AtlasError
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            self.send_response(413);self.end_headers();self.wfile.write(json.dumps(dict(error_code='payload_too_large',retryable=False,details={'size_bytes':10485761,'max_bytes':10485760,'raw_available':False,'token':'secret'})).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    p=tmp_path/'connection.json';p.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}','token':'private'}));p.chmod(0o600)
    try:
        with pytest.raises(AtlasError) as caught:AtlasClient(p).request('GET','/api/qa/a')
        assert caught.value.status==413
        assert caught.value.details=={'size_bytes':10485761,'max_bytes':10485760,'raw_available':False}
    finally:server.shutdown();server.server_close();thread.join()


def test_non_string_request_references_are_rejected(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test')
    with pytest.raises(ValueError,match='input_invalid'):s.poll([])
    with pytest.raises(ValueError,match='input_invalid'):s.ask('k','Question?','q',previous={})


def test_capture_preserves_answer_without_changing_research_and_resumes_offline(tmp_path):
    from researchclaw.codex.atlas_session import AtlasSession
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    head=store.read_head(tmp_path)['id'];posts=c.posts
    result=s.capture('k')
    assert result['answer_state']=='stored'
    assert result['received'] is False
    assert 'import_result' not in result
    assert store.read_head(tmp_path)['id']==head
    assert c.posts==posts
    def offline(*args,**kwargs):raise AssertionError('saved capture must not call Atlas')
    c.request=offline;c.identity=offline
    again=AtlasSession(tmp_path,c).capture('k')
    assert again['qa_ref']==result['qa_ref']
    assert (s.base/'objects'/result['qa_ref']['sha256']).is_file()


@pytest.mark.parametrize('status',['running','queued'])
def test_capture_does_not_promote_non_answer_job_even_with_qa_reference(tmp_path,status):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    c.jobs['k']['status']=status
    with pytest.raises(ValueError,match='atlas_qa_not_ready'):s.capture('k')
    assert not s._get('k').get('qa_envelope')


def test_capture_partial_keeps_original_status_and_missing_support(tmp_path):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    c.jobs['k']['status']='partial'
    s._supporting=lambda *args:[dict(kind='page',received=False,error='reference_mismatch')]
    result=s.capture('k')
    assert result['job']['status']=='partial'
    assert result['answer_state']=='needs_input'
    assert result['received'] is False


@pytest.mark.parametrize('status',['failed','interrupted'])
def test_capture_keeps_failed_answer_as_diagnostic_only(tmp_path,status):
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    c.jobs['k']['status']=status
    result=s.capture('k')
    assert result['answer_state']=='diagnostic_only'
    assert result['job']['status']==status
    assert result['received'] is False


def test_answer_delivery_is_durable_without_research_adoption(tmp_path):
    from researchclaw.codex.service_inbox import ServiceInbox
    s,c=session(tmp_path);s.bind('P','Test');s.ask('k','Question?','q1')
    head=store.read_head(tmp_path)['id']
    recipient=dict(work_id='work1',role_id='reviewer',round_id='initial',input_revision='v1')
    first=s.queue_answer('k',recipient)
    assert s.queue_answer('k',recipient)==first
    rows=ServiceInbox(tmp_path,s.project_id).pending()
    assert len(rows)==1
    assert rows[0]['result_ref']['qa_ref']['qa_id']=='qa-k'
    assert rows[0]['result_ref']['answer_state']=='stored'
    assert store.read_head(tmp_path)['id']==head
    assert c.posts==1
