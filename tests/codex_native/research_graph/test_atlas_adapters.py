"""Real HTTP/CLI Atlas ingestion; no external service or research execution."""
import base64
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from researchclaw.codex.research_viewer import _make_server
from researchclaw.core.research_graph import commands, store

QA = b'---\nschema_version: 1\nid: qa-test\nquestion: Which process?\nanswer: Compare conditions, not orientation causality.\nproject: null\n---\n'


def request(server, path, data=None, headers=None):
    h = {'Content-Type': 'application/json', **(headers or {})}
    req = Request(f'http://127.0.0.1:{server.server_port}{path}',
                  data=None if data is None else json.dumps(data).encode(), headers=h)
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, error.read()


@pytest.fixture
def server(tmp_path):
    root = tmp_path/'project'
    commands.init_project(root, topic='Atlas adapter', content_origin='synthetic')
    srv = _make_server(root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True); thread.start()
    yield root, srv
    srv.shutdown(); srv.server_close(); thread.join()


def encoded(data=QA):
    return base64.b64encode(data).decode()


def test_preview_is_read_only_and_import_uses_same_bytes(server):
    root, srv = server; before = store.read_head(root)['id']
    status, preview = request(srv, '/api/atlas/preview', {'content_base64': encoded()})
    assert status == 200
    assert preview['question'] == 'Which process?'
    assert store.read_head(root)['id'] == before
    payload = dict(content_base64=encoded(), sha256=preview['file_sha256'], filename='qa.md',
                   expected_head=before, command_id='import-qa')
    status, receipt = request(srv, '/api/atlas/import', payload)
    assert status == 200 and receipt['head_id'] != before
    assert request(srv, '/api/atlas/import', payload) == (200, receipt)
    status, view = request(srv, '/api/view')
    assert view['external_evidence'][0]['record']['id'] == receipt['record_id']
    assert not view['approvals']
    assert all(n['status'] == 'not_started' for n in view['nodes'])


def test_bad_origin_shape_hash_and_stale_head_do_not_mutate(server):
    root, srv = server; before = store.read_head(root)['id']
    assert request(srv, '/api/atlas/preview', {'content_base64':encoded()},
                   {'Origin':'https://outside.example'})[0] == 403
    assert request(srv, '/api/atlas/preview', {'path':'/etc/passwd'})[0] == 400
    assert request(srv, '/api/atlas/preview', {'content_base64':'!!'})[0] == 400
    payload = dict(content_base64=encoded(), sha256='0'*64, filename='qa.md',
                   expected_head=before, command_id='bad-hash')
    assert request(srv, '/api/atlas/import', payload)[0] == 400
    assert store.read_head(root)['id'] == before
    payload['sha256'] = store._hash(QA)
    assert request(srv, '/api/atlas/import', payload)[0] == 200
    payload.update(command_id='stale', content_base64=encoded(QA+b'new'),sha256=store._hash(QA+b'new'))
    assert request(srv, '/api/atlas/import', payload)[0] == 409


def test_usage_decision_followup_roundtrip(server):
    root, srv = server; before=store.read_head(root)['id']
    assert request(srv,'/api/atlas/import',dict(content_base64=encoded(),sha256=store._hash(QA),
      filename='qa.md',expected_head=before,command_id='import'))[0]==200
    view=request(srv,'/api/view')[1]; ref=view['external_evidence'][0]['ref']
    usage=dict(evidence_ref=ref,question_ref=ref,status='limited',allowed_uses=['Process comparison'],
      held_uses=['Orientation causality'],limitations=['One paper'],rationale='Question can be scoped',
      expected_head=view['head_id'],command_id='review')
    status,result=request(srv,'/api/atlas/review',usage);assert status==200,result
    view=request(srv,'/api/view')[1];review=view['external_reviews'][0]['ref']
    decision=dict(review_ref=review,title='Two conditions',conclusion='Design process comparison',
      rationale='No structure measurement',limitations=['Design only'],submission_refs=[],prior_ref=None,
      expected_head=view['head_id'],command_id='decision')
    status,result=request(srv,'/api/atlas/decision',decision);assert status==200,result
    view=request(srv,'/api/view')[1];dr=view['external_decisions'][0]['ref']
    question=dict(decision_ref=dr,question='What measurement direction?',missing_evidence='Electrodes',
      decision_impact='Comparability',scope='Abbasi methods',expected_head=view['head_id'],command_id='question')
    status,result=request(srv,'/api/atlas/question',question);assert status==200,result
    view=request(srv,'/api/view')[1]
    assert view['external_questions'][0]['record']['question']==question['question']
    assert view['external_decisions'][0]['record']['review_status']=='coordinator_only'


def test_cli_preview_and_import(tmp_path,capsys):
    from researchclaw.codex.cli import main
    root=tmp_path/'project'; qa=tmp_path/'qa.md';qa.write_bytes(QA)
    before=commands.init_project(root,topic='CLI',content_origin='synthetic')['id']
    args=['research','atlas-import',str(root),str(qa),'--json']
    assert main([*args,'--preview'])==0
    assert json.loads(capsys.readouterr().out)['id']=='qa-test'
    assert store.read_head(root)['id']==before
    assert main([*args,'--expected-head',before,'--command-id','cli-qa'])==0
    out=json.loads(capsys.readouterr().out)
    assert out['record_id'] and out['head_id']!=before


def test_http_rejects_unsupported_media_and_oversized_requests(server):
    import http.client
    from researchclaw.codex.atlas_http import MAX_REQUEST_BYTES
    root,srv=server;before=store.read_head(root)['id']
    assert request(srv,'/api/atlas/preview',{'content_base64':encoded()},
                   {'Content-Type':'text/plain'})[0]==400
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=5)
    conn.putrequest('POST','/api/atlas/preview')
    conn.putheader('Content-Type','application/json')
    conn.putheader('Content-Length',str(MAX_REQUEST_BYTES+1));conn.endheaders()
    assert conn.getresponse().status==413;conn.close()
    assert store.read_head(root)['id']==before


def test_http_rejects_duplicate_json_keys_and_preserves_view(server):
    import http.client
    root,srv=server;before=store.read_head(root)['id']
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=5)
    conn.request('POST','/api/atlas/preview',body=b'{"content_base64":"","content_base64":""}',
                 headers={'Content-Type':'application/json'})
    assert conn.getresponse().status==400;conn.close()
    assert request(srv,'/api/view')[0]==200
    assert store.read_head(root)['id']==before


def test_absurd_content_length_is_rejected_without_disconnecting(server):
    import http.client
    root,srv=server;before=store.read_head(root)['id']
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=5)
    conn.putrequest('POST','/api/atlas/preview')
    conn.putheader('Content-Type','application/json');conn.putheader('Content-Length','9'*5000);conn.endheaders()
    assert conn.getresponse().status==413;conn.close()
    assert store.read_head(root)['id']==before


def test_deep_json_returns_400_and_keeps_server_available(server):
    import http.client
    root,srv=server;before=store.read_head(root)['id']
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=5)
    body=b'{"content_base64":'+b'['*10000+b'0'+b']'*10000+b'}'
    conn.request('POST','/api/atlas/preview',body=body,headers={'Content-Type':'application/json'})
    response=conn.getresponse()
    assert response.status==400
    assert json.loads(response.read())['error']=='atlas_json_invalid';conn.close()
    assert request(srv,'/api/view')[0]==200
    assert store.read_head(root)['id']==before
