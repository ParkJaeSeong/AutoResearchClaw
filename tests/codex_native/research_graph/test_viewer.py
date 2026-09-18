"""U1 loopback GET-only viewer, pinned raw reads and CLI adapters."""
import importlib
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.research_graph import store
from tests.codex_native.research_graph.test_m1_scope import Fixture, uid


def api():
    return importlib.import_module('researchclaw.codex.research_viewer')


def fetch(server, path, method='GET', headers=None):
    request = Request(f'http://127.0.0.1:{server.server_port}{path}', method=method, headers=headers or {})
    try:
        with urlopen(request) as response:
            return response.status, response.read(), response.headers
    except HTTPError as error:
        return error.code, error.read(), error.headers


def test_loopback_view_and_pinned_raw_are_get_only_and_preserve_files(tmp_path):
    f = Fixture(tmp_path / 'project'); f.register(); old = f.head['id']; f.council_prepare(); hidden = f.submit(0, 'initial', rationale='SERVER PRIVATE')
    server = api()._make_server(f.root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    before = {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
    try:
        status, body, headers = fetch(server, f'/api/view?head={old}')
        assert status == 200 and headers['Cache-Control'] == 'no-store'
        view = json.loads(body); assert view['head_id'] == old and view['current_head_id'] == f.head['id']
        status, raw, _ = fetch(server, view['artifacts'][0]['raw_url'])
        assert status == 200 and json.loads(raw)['node'] == 'scope'
        assert hidden['id'].encode() not in body and b'SERVER PRIVATE' not in body
        assert fetch(server, '/api/artifacts/' + store._hash(store._canonical(hidden)))[0] == 404
        assert fetch(server, '/api/view?head=' + '0' * 64)[0] == 409
        assert fetch(server, '/api/view?head=a&head=b')[0] == 400
        assert fetch(server, '/api/view?extra=1')[0] == 400
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'HEAD'):
            assert fetch(server, '/api/view', method)[0] == 405
        for path in ('/HEAD.json', '/api/state', '/%2e%2e/HEAD.json', '/app.js/other'):
            assert fetch(server, path)[0] in (400, 404)
        assert fetch(server, '/api/view', headers={'Origin': 'https://outside.example'})[0] == 403
        assert fetch(server, '/api/view', headers={'Host': 'outside.example'})[0] == 403
    finally:
        server.shutdown(); server.server_close(); thread.join()
    assert {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()} == before


def test_server_static_allowlist_and_nonloopback_refusal(tmp_path, monkeypatch):
    f = Fixture(tmp_path / 'project')
    with pytest.raises(ValueError, match='^research_viewer_host_invalid$'):
        api()._make_server(f.root, host='0.0.0.0', port=0)
    assets = tmp_path / 'static'; assets.mkdir(); (assets / 'index.html').write_text('<p>Safe static fixture</p>')
    (assets / 'secret.txt').write_text('NOT ALLOWED')
    for name in ('timeline.js', 'trace.js'):
        (assets / name).write_text('export const fixture = true;')
    monkeypatch.setattr(api(), '_STATIC_ROOT', assets)
    server = api()._make_server(f.root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        assert fetch(server, '/')[0] == 200
        assert fetch(server, '/secret.txt')[0] == 404
        for name in ('timeline.js', 'trace.js'):
            assert fetch(server, '/' + name)[0] == 200
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_cli_apply_inspect_historical_packet_and_replay_never_return_raw_state(tmp_path, capsys):
    f = Fixture(tmp_path / 'project'); initial = f.head['id']; payload = tmp_path / 'node.json'
    payload.write_text(json.dumps({'artifact': f.artifact}))
    command = ['research', 'apply', str(f.root), '--operation', 'm1.node.register', '--payload', str(payload),
               '--expected-head', initial, '--command-id', 'register-node', '--json']
    assert main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert 'state' not in first and 'events' not in first and 'objects' not in first
    assert main(command) == 0 and json.loads(capsys.readouterr().out) == first
    f.head = store.read_head(f.root); f.council_prepare(); hidden = f.submit(0, 'initial', rationale='CLI PRIVATE')
    assert main(['research', 'inspect', str(f.root), '--head', initial, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['head_id'] == initial
    assert main(['research', 'packet', str(f.root), '--assignment', f.reviewers[1]['id'], '--json']) == 0
    packet = capsys.readouterr().out
    assert hidden['id'] not in packet and 'CLI PRIVATE' not in packet and 'own_submissions' in packet
    assert main(['research', 'packet', str(f.root), '--assignment', f.reviewers[0]['id'], '--json']) == 0
    assert 'CLI PRIVATE' in capsys.readouterr().out
    malformed = tmp_path / 'bad.json'; malformed.write_text('{"artifact":{},"artifact":{}}')
    assert main(['research', 'apply', str(f.root), '--operation', 'm1.node.register', '--payload', str(malformed),
                 '--expected-head', f.head['id'], '--command-id', uid()]) == 2
    assert 'research_graph_request_failed' in capsys.readouterr().err


def test_cli_view_uses_loopback_server(tmp_path, monkeypatch, capsys):
    f = Fixture(tmp_path / 'project'); calls = []
    monkeypatch.setattr(api(), 'serve_view', lambda root, **kw: calls.append((root, kw)))
    assert main(['research', 'view', str(f.root), '--port', '8123']) == 0
    assert calls == [(f.root, {'host': '127.0.0.1', 'port': 8123})]


def test_execution_module_is_served_by_http(tmp_path):
    f = Fixture(tmp_path / 'execution-assets')
    server = api()._make_server(f.root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, headers = fetch(server, '/execution.js')
        assert status == 200
        assert 'javascript' in headers['Content-Type']
        assert b'export function renderExecutions' in body
    finally:
        server.shutdown(); server.server_close(); thread.join()
