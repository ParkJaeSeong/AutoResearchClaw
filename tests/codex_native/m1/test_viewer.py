import importlib
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest
from researchclaw.core.m1.project import init_project
from researchclaw.core.m1.packets import prepare_node, register_outputs
from researchclaw.core.m1.store import read_head
from tests.codex_native.m1.helpers import submission

@pytest.fixture
def viewer(tmp_path, monkeypatch):
    try:
        module = importlib.import_module('researchclaw.codex.m1_viewer')
    except ModuleNotFoundError:
        pytest.fail('local viewer implementation is missing')
    root = tmp_path / 'project'
    init_project(root, topic='synthetic viewer check', profile='materials_ai', max_returns=2, content_origin='synthetic')
    packet = prepare_node(root, 'scope', command_id='prepare')['packet']
    files = {'scope/goal.md':b'<script>window.pwned=true</script>', 'scope/constraints.json':b'{}'}
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files), command_id='register')
    refs = result['artifacts']
    visible = [ref for ref in refs if ref['logical_path']=='scope/goal.md']
    monkeypatch.setattr(module, '_read_view', lambda path: {'head_id':read_head(path)['id'], 'artifacts':visible})
    server = module._make_server(root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = 'http://127.0.0.1:' + str(server.server_port)
    yield module, root, refs, visible, url
    server.shutdown();server.server_close();thread.join(timeout=2)

def fetch(url, path='/', method='GET', headers=None):
    try:
        response=urlopen(Request(url+path, method=method, headers=headers or {}), timeout=3)
    except HTTPError as error:
        response=error
    with response:
        return response.status, response.headers, response.read()

def test_registered_visible_artifact_only_as_inert_text(viewer):
    _,root,refs,visible,url=viewer
    code,headers,body=fetch(url, '/api/artifacts/'+visible[0]['id'])
    assert code==200 and body.startswith(b'<script>')
    assert headers['Content-Type'].startswith('text/plain')
    assert headers['X-Content-Type-Options']=='nosniff'
    hidden=next(r for r in refs if r not in visible)
    assert fetch(url, '/api/artifacts/'+hidden['id'])[0]==404
    assert fetch(url, '/api/artifacts/missing')[0]==404

def test_host_origin_and_all_write_methods_are_rejected(viewer):
    *_,url=viewer
    assert fetch(url, '/api/view', headers={'Host':'evil.example'})[0]==403
    assert fetch(url, '/api/view', headers={'Origin':'https://evil.example'})[0]==403
    assert fetch(url, '/api/view', headers={'Origin':url})[0]==200
    for method in ('POST','PUT','PATCH','DELETE','OPTIONS','TRACE'):
        assert fetch(url, '/api/view', method=method)[0]==405

def test_routes_do_not_offer_filesystem_or_project_switching(viewer):
    *_,url=viewer
    for path in ('/.researchclaw/m1/HEAD.json','/../pyproject.toml','/%2e%2e/pyproject.toml','/api/view?root=/tmp','/package.json'):
        assert fetch(url,path)[0] in (400,404)
    code,headers,body=fetch(url)
    assert code==200 and b'research-app' in body
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
    assert headers['Cache-Control']=='no-store'
    assert fetch(url,'/live.js')[0]==200

def test_view_and_artifact_reads_leave_project_unchanged(viewer):
    _,root,_,visible,url=viewer
    def snapshot():
        return {str(p.relative_to(root)):(p.stat().st_mtime_ns,p.stat().st_mode,p.read_bytes() if p.is_file() else None) for p in root.rglob('*')}
    before=snapshot()
    assert json.loads(fetch(url,'/api/view')[2])['head_id']==read_head(root)['id']
    assert fetch(url,'/api/artifacts/'+visible[0]['id'])[0]==200
    assert snapshot()==before

def test_only_explicit_loopback_bind_is_allowed(viewer):
    module,root,*_=viewer
    assert module.is_allowed_host('127.0.0.1')
    for host in ('0.0.0.0','localhost','::1','example.org'):
        assert not module.is_allowed_host(host)
        with pytest.raises(ValueError,match='m1_viewer_host_invalid'):
            module._make_server(root,host=host,port=0)

def test_projection_id_cannot_be_used_as_raw_object_permission(viewer, monkeypatch):
    module,root,_,visible,url=viewer
    projected=dict(visible[0], id='H1-r1', source_artifact_id=visible[0]['id'])
    monkeypatch.setattr(module, '_read_view', lambda path: {'artifacts':[projected]})
    assert fetch(url,'/api/artifacts/H1-r1')[0]==404
    assert fetch(url,'/api/artifacts/'+visible[0]['id'])[0]==404

def test_artifact_integrity_failure_does_not_serve_corrupted_bytes(viewer):
    module,root,_,visible,url=viewer
    ref=visible[0]
    path=module.store._store_path(root)/'objects'/ref['sha256']
    path.write_bytes(b'corrupted private data')
    status,_,body=fetch(url,'/api/artifacts/'+ref['id'])
    assert status==409
    assert b'corrupted private data' not in body

def test_view_cli_dispatches_fixed_root_and_port_without_json_after_shutdown(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    from researchclaw.codex.cli import main
    from researchclaw.codex import m1_viewer
    seen=[]
    def serve(root, *, host='127.0.0.1', port=0):
        seen.append((root,host,port))
        print('http://127.0.0.1:54321/')
    monkeypatch.setattr(m1_viewer,'serve_view',serve)
    result=main(['m1','view',str(tmp_path),'--port','54321'])
    captured=capsys.readouterr()
    assert result==0
    assert seen==[(Path(tmp_path),'127.0.0.1',54321)]
    assert captured.out=='http://127.0.0.1:54321/\n'
    assert captured.err==''


def test_real_registered_projection_is_served_without_mutation(viewer, monkeypatch):
    module, root, refs, _, url = viewer
    from researchclaw.core.m1.views import build_view
    monkeypatch.setattr(module, '_read_view', build_view)
    before = {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes())
              for p in root.rglob('*') if p.is_file()}
    status, _, body = fetch(url, '/api/view')
    assert status == 200
    view = json.loads(body)
    assert view == build_view(root)
    assert view['data_origin'] == 'registered'
    for ref in refs:
        assert fetch(url, '/api/artifacts/' + ref['id'])[0] == 200
    assert before == {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes())
                      for p in root.rglob('*') if p.is_file()}
