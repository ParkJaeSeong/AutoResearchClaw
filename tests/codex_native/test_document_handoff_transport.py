import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from researchclaw.codex.document_handoff_transport import HandoffHTTP, TransportError


def test_http_lost_submit_recovers_receipt_without_second_conversion(tmp_path):
    original=b'<article>fixture</article>';p=tmp_path/'paper.xml';p.write_bytes(original)
    state={'receipt':None,'posts':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value):
            raw=json.dumps(value).encode();self.send_response(status);self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            assert self.headers['Authorization']=='Bearer synthetic-token'
            assert 'operation=convert.jats' in self.path
            self.reply(200,state['receipt']) if state['receipt'] else self.reply(404,{'error':{'code':'RECEIPT_NOT_FOUND'}})
        def do_POST(self):
            state['posts']+=1
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert base64.b64decode(data['xml_base64'])==original
            state['receipt']={'task_id':'t','operation':'convert.jats','request_key':'k'}
            self.connection.shutdown(2);self.connection.close()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config=tmp_path/'connection.json';config.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}','token':'synthetic-token'}));config.chmod(0o600)
    client=HandoffHTTP(config)
    row={'operation':'convert.jats','request_key':'k','documents_request':{'config_revision':'cfg','retrieval_consumer_id':'atlas','original_path':str(p),'filename':'paper.xml'},'atlas_request':{'source':{'sha256':hashlib.sha256(original).hexdigest(),'filename':'paper.xml'}}}
    try:
        with pytest.raises(TransportError):client.recover_or_submit(row)
        assert client.recover_or_submit(row)['task_id']=='t'
        assert state['posts']==1
    finally:server.shutdown();server.server_close();thread.join()


def test_actual_http_atlas_submit_poll_result_and_ack(tmp_path):
    from tests.codex_native.test_document_handoff_adapter import setup
    from researchclaw.codex.document_handoff_adapter import HandoffAdapter
    from urllib.parse import urlsplit,parse_qs
    j,d,a,_=setup(tmp_path)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def run_request(self,method):
            assert self.headers['Authorization']=='Bearer consumer-test-token'
            url=urlsplit(self.path);params={k:v[0] for k,v in parse_qs(url.query).items()}
            body=json.loads(self.rfile.read(int(self.headers['Content-Length']))) if method=='POST' else None
            raw=json.dumps(a.request(method,url.path,body,params)).encode()
            self.send_response(200);self.end_headers();self.wfile.write(raw)
        def do_GET(self):self.run_request('GET')
        def do_POST(self):self.run_request('POST')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    path=tmp_path/'atlas-private.json';path.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}','token':'consumer-test-token'}));path.chmod(0o600)
    try:
        s=HandoffAdapter(j,d,HandoffHTTP(path));s.advance()
        a.phase='terminal';a.updated=2
        a.result=dict(import_id='i',documents_result_ref={'instance_id':'D','task_id':'t','result_revision':'r1','manifest_sha256':'d'*64},source_refs=[],extraction_refs=[],page_refs=[],read_scope='methods',unresolved=['figure unavailable'],index_status={},ingest_job_ref='job')
        s.poll();s.poll()
        assert a.acked and not j.pending_events() and not j.pending_acks()
        assert b'consumer-test-token' not in j.path.read_bytes()
    finally:server.shutdown();server.server_close();thread.join()
