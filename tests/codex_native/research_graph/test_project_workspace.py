import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from researchclaw.codex.project_workspace import Workspace, public_files, public_file
from researchclaw.codex.research_viewer import _make_server
from researchclaw.core.research_graph import commands, store


def request(server, path, payload=None, headers=None):
    req = Request(f'http://127.0.0.1:{server.server_port}{path}',
                  data=None if payload is None else json.dumps(payload).encode(),
                  headers=headers or ({'Content-Type': 'application/json'} if payload is not None else {}))
    try:
        with urlopen(req) as response: return response.status, response.read()
    except HTTPError as error: return error.code, error.read()


def test_create_replay_conflict_and_policy(tmp_path):
    workspace = Workspace(tmp_path / 'workspace')
    payload = dict(name='Display / name', topic='Question?', request_id=str(uuid4()))
    first = workspace.create(payload)
    assert workspace.create(payload) == first
    assert len(workspace.read()['projects']) == 1
    root = workspace.resolve(first['id'])
    state = store.read_head(root)['state']
    assert state['return_policy']['mode'] == 'evidence_driven'
    assert state['project_id'] == first['id']
    assert (root / 'outputs/M3').is_dir()
    assert not state.get('work_episodes')
    with pytest.raises(ValueError, match='conflict'):
        workspace.create({**payload, 'name': 'changed'})
    for payload in ({}, {**payload, 'root': '/tmp'}, {**payload, 'name': ''}):
        with pytest.raises(ValueError): workspace.create(payload)


def test_create_recovers_before_catalog_publication(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'workspace')
    payload = dict(name='A', topic='B', request_id='retry')
    original = workspace.write
    calls = []
    def interrupted_write(data):
        calls.append(data)
        if len(calls) == 2: raise OSError('interrupted')
        original(data)
    monkeypatch.setattr(workspace, 'write', interrupted_write)
    with pytest.raises(OSError): workspace.create(payload)
    monkeypatch.setattr(workspace, 'write', original)
    with pytest.raises(ValueError, match='conflict'):
        workspace.create({**payload, 'name': 'changed'})
    entry = workspace.create(payload)
    assert workspace.create(payload) == entry
    assert len(workspace.read()['projects']) == 1


def test_public_files_exclude_private_hidden_and_symlink_paths(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    (root / 'documents').mkdir(); (root / 'documents/a.txt').write_text('public')
    (root / '.researchclaw').mkdir(); (root / '.researchclaw/secret').write_text('secret')
    (root / 'documents/link').symlink_to(root / '.researchclaw/secret')
    (root / 'documents/escape').symlink_to(tmp_path, target_is_directory=True)
    (root / 'documents/.secret').write_text('hidden')
    files = public_files(root, 'project')['files']
    assert [f['path'] for f in files] == ['documents/a.txt']
    for name in ('../x', 'documents/../.researchclaw/secret', '.researchclaw/secret', 'documents/link', 'documents/escape/x', 'runs/x', 'documents/.secret'):
        with pytest.raises(ValueError): public_file(root, name)


def test_http_projects_isolation_unknown_and_public_download(tmp_path):
    root = tmp_path / 'legacy'; initial = commands.init_project(root, topic='Legacy', content_origin='real')
    workspace = Workspace(tmp_path / 'workspace')
    server = _make_server(root, host='127.0.0.1', port=0, workspace=workspace.path)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        status, body = request(server, '/api/projects')
        assert status == 200
        assert json.loads(body)['default_project_id'] == initial['state']['project_id']
        payload = dict(name='Second', topic='Another question', request_id='create')
        status, body = request(server, '/api/projects', payload)
        assert status == 200, body
        project = json.loads(body)['project']; project_id = project['id']
        assert request(server, '/?project=' + project_id + '&head=' + initial['id'])[0] == 200
        target = workspace.resolve(project_id)
        (target / 'documents/public.txt').write_text('second project only')
        status, body = request(server, '/api/view?project=' + project_id)
        assert status == 200 and json.loads(body)['project']['topic'] == 'Another question'
        assert request(server, '/api/view?project=' + str(uuid4()))[0] == 404
        assert request(server, '/api/view?project=../bad')[0] == 404
        assert request(server, '/api/view?project=a&project=b')[0] == 400
        status, body = request(server, '/api/project-files?project=' + project_id)
        files = json.loads(body)['files']; assert len(files) == 1
        assert request(server, files[0]['url']) == (200, b'second project only')
        assert request(server, '/api/project-files/documents/public.txt')[0] == 404
        assert request(server, '/api/project-files/.researchclaw/HEAD.json?project=' + project_id)[0] == 404
        assert request(server, '/api/projects', payload, {'Content-Type':'application/json', 'Origin':'https://evil.example'})[0] == 403
        assert request(server, '/api/projects', {**payload, 'name':'changed'})[0] == 409
        assert request(server, '/api/episodes/review?project=' + str(uuid4()), {})[0] == 404
        assert request(server, '/api/atlas/preview?project=' + str(uuid4()), {})[0] == 404
        assert store.read_head(root)['id'] == initial['id']
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_project_bound_review_writes_only_selected_root(tmp_path):
    from tests.codex_native.research_graph.test_work_episodes import start_payload, conclude_payload
    first = tmp_path / 'first'; second = tmp_path / 'second'
    initial = commands.init_project(first, topic='first', content_origin='synthetic')
    head = commands.init_project(second, topic='second', content_origin='synthetic')
    workspace = Workspace(tmp_path / 'workspace')
    entry = workspace.register(second, name='second')
    for op, payload, key in [('episode.start', start_payload('review', review_required=True), 'start'), ('episode.conclude', conclude_payload('review'), 'finish')]:
        head = commands.apply_command(second, operation=op, payload=payload, expected_head=head['id'], command_id=key)
    server = _make_server(first, host='127.0.0.1', port=0, workspace=workspace.path)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        payload = dict(id='review', decision='continue', feedback='Proceed with the preparation.', expected_head=head['id'], command_id='ui-review')
        assert request(server, '/api/episodes/review?project=' + entry['id'], payload)[0] == 200
        assert store.read_head(second)['state']['work_episodes']['review']['review_status'] == 'continued'
        assert store.read_head(first)['id'] == initial['id']
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_legacy_projects_lists_default_without_management(tmp_path):
    initial = commands.init_project(tmp_path, topic='Legacy', content_origin='synthetic')
    server = _make_server(tmp_path, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        status, body = request(server, '/api/projects')
        data = json.loads(body)
        assert status == 200 and data['management_enabled'] is False
        assert data['projects'][0]['id'] == initial['state']['project_id']
        assert request(server, '/api/projects', dict(name='x',topic='y',request_id='z'))[0] == 405
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_archive_preserves_research_and_can_restore(tmp_path):
    workspace = Workspace(tmp_path / 'workspace')
    entry = workspace.create(dict(name='Old', topic='Old question', request_id='old'))
    root = workspace.resolve(entry['id'])
    before = store.read_head(root)['id']
    archived = workspace.set_archived(entry['id'], True)
    assert archived['archived'] is True
    assert workspace.set_archived(entry['id'], True) == archived
    assert workspace.resolve(entry['id']) == root
    assert store.read_head(root)['id'] == before
    assert workspace.register(root, name='Old', layout='managed')['archived'] is True
    assert workspace.set_archived(entry['id'], False)['archived'] is False
    with pytest.raises(ValueError):
        workspace.set_archived(str(uuid4()), True)
    with pytest.raises(ValueError):
        workspace.set_archived(entry['id'], 'true')
