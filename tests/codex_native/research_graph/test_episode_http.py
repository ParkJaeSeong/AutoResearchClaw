import json
import threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
from researchclaw.core.research_graph import commands,store
from researchclaw.codex.research_viewer import _make_server
from tests.codex_native.research_graph.test_work_episodes import start_payload,conclude_payload

@pytest.fixture
def server(tmp_path):
    head=commands.init_project(tmp_path,topic='UI review synthetic',content_origin='synthetic')
    for op,payload,key in [('episode.start',start_payload('review',review_required=True),'start'),('episode.conclude',conclude_payload('review'),'finish')]:
        head=commands.apply_command(tmp_path,operation=op,payload=payload,expected_head=head['id'],command_id=key)
    s=_make_server(tmp_path,host='127.0.0.1',port=0)
    t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
    yield s,tmp_path,head
    s.shutdown();s.server_close();t.join()

def post(server,payload,headers=None):
    s,_,_=server
    request=Request(f'http://127.0.0.1:{s.server_port}/api/episodes/review',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with urlopen(request) as response:return response.status,json.loads(response.read())
    except HTTPError as error:return error.code,error.read()

def body(server,**changes):
    value=dict(id='review',decision='continue',feedback='의견을 확인했습니다. 다음 준비를 진행하세요.')
    return {**value,'expected_head':server[2]['id'],'command_id':'ui-review',**changes}

def test_review_is_persisted_once_and_replay_returns_same_receipt(server):
    payload=body(server)
    status,result=post(server,payload)
    assert status==200
    assert result['review_status']=='continued'
    assert result['review']['reviewer']=='local-ui-user'
    head=store.read_head(server[1])
    assert post(server,payload)==(200,result)
    assert store.read_head(server[1])==head
    assert len(head['state']['work_followups'])==1
    assert head['state']['work_episodes']['review']['conclusion']==server[2]['state']['work_episodes']['review']['conclusion']

@pytest.mark.parametrize('patch',[{'reviewer':'forged'},{'operation':'m1.handoff.accept'},{'decision':'approve'},{'feedback':''}])
def test_invalid_payload_does_not_write(server,patch):
    before=store.read_head(server[1])
    assert post(server,body(server,**patch))[0]==400
    assert store.read_head(server[1])==before

def test_origin_conflict_and_second_review_are_rejected(server):
    assert post(server,body(server),{'Origin':'https://outside.example'})[0]==403
    assert post(server,body(server,expected_head='0'*64))[0]==409
    assert post(server,body(server))[0]==200
    head=store.read_head(server[1])
    assert post(server,body(server,expected_head=head['id'],command_id='new-review',decision='revise'))[0]==409
    assert store.read_head(server[1])==head

def test_oversized_request_rejected(server):
    assert post(server,body(server,feedback='x'*65536))[0]==413

@pytest.mark.parametrize('decision',['continue','revise'])
def test_ui_review_controls_dependent_episode_without_starting_it(server,decision):
    assert post(server,body(server,decision=decision))[0]==200
    head=store.read_head(server[1])
    assert len(head['state']['work_episodes'])==1
    def start_next():
        return commands.apply_command(server[1],operation='episode.start',payload=start_payload('next',depends_on=['review']),expected_head=head['id'],command_id='next')
    if decision=='continue':
        assert start_next()['state']['work_episodes']['next']['execution_status']=='running'
    else:
        with pytest.raises(ValueError,match='episode_dependency_revision_requested'):start_next()
        assert store.read_head(server[1])==head

def raw_post(server,data,extra_length=0):
    import socket
    port=server[0].server_port
    with socket.create_connection(('127.0.0.1',port),timeout=2) as connection:
        connection.sendall((f'POST /api/episodes/review HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(data)+extra_length}\r\n\r\n').encode()+data)
        connection.shutdown(socket.SHUT_WR)
        response=b''
        while chunk:=connection.recv(65536):response+=chunk
    return response

@pytest.mark.parametrize('kind',['short','duplicate','nested'])
def test_malformed_json_never_writes(server,kind):
    before=store.read_head(server[1]);data=json.dumps(body(server)).encode()
    if kind=='duplicate':data=data.replace(b'"decision": "continue"',b'"decision":"continue","decision":"revise"')
    if kind=='nested':data=b'['*1200+b'0'+b']'*1200
    response=raw_post(server,data,1 if kind=='short' else 0)
    assert b' 400 ' in response.split(b'\r\n')[0]
    assert store.read_head(server[1])==before

def test_lost_response_after_commit_returns_uncertain_then_replays(server,monkeypatch):
    from researchclaw.codex import episode_http
    original=episode_http.commands.apply_command
    failed=False
    def lose(*args,**kwargs):
        nonlocal failed
        result=original(*args,**kwargs)
        if not failed:
            failed=True
            raise OSError('private-storage-detail')
        return result
    monkeypatch.setattr(episode_http.commands,'apply_command',lose)
    status,error=post(server,body(server))
    assert status==503 and b'private-storage-detail' not in error
    head=store.read_head(server[1])
    assert post(server,body(server))[0]==200
    assert store.read_head(server[1])==head
