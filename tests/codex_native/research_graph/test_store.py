from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import store, commands


def state():
    return {**store._VERSION, 'project_id': str(uuid4()), 'content_origin': 'synthetic', 'topic': 'test'}


def event(name='initialized'):
    return {**store._VERSION, 'type': name, 'payload': {}}


def init(root):
    return store.initialize_record(root, command_id='init', state=state(), event=event(), objects={'source': b'original'})


def test_replay_conflict_stale_and_immutable(tmp_path):
    first = init(tmp_path)
    args = dict(expected_head=first['id'], command_id='second', state=first['state'], event=event('second'), objects={'next': b'next'})
    second = store.commit_record(tmp_path, **args)
    third = store.commit_record(tmp_path, **{**args, 'expected_head': second['id'], 'command_id': 'third', 'event': event('third')})
    assert store.commit_record(tmp_path, **args) == second
    for patch, reason in [({'event': event('different')}, 'command_conflict'), ({'command_id': 'stale'}, 'head_conflict')]:
        with pytest.raises(ValueError, match=reason): store.commit_record(tmp_path, **{**args, **patch})
        assert store.read_head(tmp_path) == third
    assert (tmp_path / '.researchclaw/research_graph/objects' / store._hash(b'original')).read_bytes() == b'original'


def test_atomic_genesis_retry_and_failure(tmp_path, monkeypatch):
    args = dict(command_id='import', state=state(), event=event(), objects={'source': b'original'})
    original = store._atomic_head
    monkeypatch.setattr(store, '_atomic_head', lambda *a: (_ for _ in ()).throw(OSError('failure')))
    with pytest.raises(OSError): store.initialize_record(tmp_path, **args)
    assert not (tmp_path / '.researchclaw/research_graph/HEAD.json').exists()
    monkeypatch.setattr(store, '_atomic_head', original)
    receipt = store.initialize_record(tmp_path, **args)
    assert store.initialize_record(tmp_path, **args) == receipt
    with pytest.raises(ValueError, match='conflict'): store.initialize_record(tmp_path, **{**args, 'objects': {}})


@pytest.mark.parametrize('entry', ['.researchclaw/m1', '.researchclaw/state.json', 'unrelated'])
def test_reject_foreign_root(tmp_path, entry):
    target = tmp_path / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('preserve')
    with pytest.raises(ValueError): init(tmp_path)
    assert target.read_text() == 'preserve'


def test_symlink_and_corruption_rejected(tmp_path):
    head = init(tmp_path)
    blob = tmp_path / '.researchclaw/research_graph/objects' / store._hash(b'original')
    blob.write_bytes(b'changed')
    with pytest.raises(ValueError, match='store_corrupt'): store.read_head(tmp_path)
    blob.unlink()
    blob.symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError): store.read_head(tmp_path)


def test_concurrent_commit_one_winner(tmp_path):
    head = init(tmp_path)
    def run(n):
        try:
            return store.commit_record(tmp_path, expected_head=head['id'], command_id=str(n), state=head['state'], event=event(str(n)), objects={})
        except ValueError as exc: return str(exc)
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(run, [1, 2]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert 'research_graph_head_conflict' in results


def test_commands_registry_replay_and_unknown(tmp_path, monkeypatch):
    head = init(tmp_path)
    with pytest.raises(ValueError, match='unknown_operation'):
        commands.apply_command(tmp_path, operation='arbitrary', payload={}, expected_head=head['id'], command_id='bad')
    def handler(snapshot, payload):
        return dict(state_patch={'topic': payload['topic']}, event=event('changed'), object_inputs={})
    monkeypatch.setitem(commands._HANDLERS, 'test.change', handler)
    args = dict(operation='test.change', payload={'topic': 'new'}, expected_head=head['id'], command_id='change')
    receipt = commands.apply_command(tmp_path, **args)
    assert commands.apply_command(tmp_path, **args) == receipt
    with pytest.raises(ValueError, match='command_conflict'):
        commands.apply_command(tmp_path, **{**args, 'payload': {'topic': 'other'}})
    assert store.read_head(tmp_path) == receipt


def test_concurrent_initialization_same_genesis(tmp_path):
    def run(_):
        return commands.init_project(tmp_path, topic='same', content_origin='synthetic')
    with ThreadPoolExecutor(8) as pool:
        receipts = list(pool.map(run, range(16)))
    assert all(r == receipts[0] for r in receipts)


def test_retry_after_publication_fsync_failure(tmp_path, monkeypatch):
    first = init(tmp_path)
    args = dict(expected_head=first['id'], command_id='second', state=first['state'], event=event('second'), objects={})
    original = store._fsync_directory
    base = tmp_path / '.researchclaw/research_graph'
    def fail(path):
        if path == base: raise OSError('fsync')
        original(path)
    monkeypatch.setattr(store, '_fsync_directory', fail)
    with pytest.raises(OSError): store.commit_record(tmp_path, **args)
    published = store.read_head(tmp_path)
    assert published['id'] != first['id']
    with pytest.raises(OSError): store.commit_record(tmp_path, **args)
    monkeypatch.setattr(store, '_fsync_directory', original)
    assert store.commit_record(tmp_path, **args) == published


def test_prepublication_commit_failure_preserves_head(tmp_path, monkeypatch):
    first = init(tmp_path)
    monkeypatch.setattr(store, '_atomic_head', lambda *a: (_ for _ in ()).throw(OSError('failure')))
    with pytest.raises(OSError):
        store.commit_record(tmp_path, expected_head=first['id'], command_id='second', state=first['state'], event=event('second'), objects={'new': b'new'})
    assert store.read_head(tmp_path) == first


@pytest.mark.parametrize('patch', [{'project_id': 'invalid'}, {'workflow_version': 'm1-v1'}, {'schema_version': True}, {'project_id': str(uuid4())}])
def test_identity_version_rejected_without_head_change(tmp_path, patch):
    first = init(tmp_path)
    with pytest.raises(ValueError):
        store.commit_record(tmp_path, expected_head=first['id'], command_id='bad', state={**first['state'], **patch}, event=event('bad'), objects={})
    assert store.read_head(tmp_path) == first


def test_init_publication_during_preflight_replays(tmp_path, monkeypatch):
    original = store._check_new_root
    def raced(root):
        monkeypatch.setattr(store, '_check_new_root', original)
        commands.init_project(root, topic='same', content_origin='synthetic')
        original(root)
    monkeypatch.setattr(store, '_check_new_root', raced)
    receipt = commands.init_project(tmp_path, topic='same', content_origin='synthetic')
    assert receipt == store.read_head(tmp_path)


def test_dispatch_replay_after_new_head_does_not_invoke_handler(tmp_path, monkeypatch):
    head = init(tmp_path)
    calls = []
    def handler(snapshot, payload):
        calls.append(payload['topic'])
        return dict(state_patch={'topic': payload['topic']}, event=event('changed'), object_inputs={})
    monkeypatch.setitem(commands._HANDLERS, 'test.replay', handler)
    first_args = dict(operation='test.replay', payload={'topic': 'first'}, expected_head=head['id'], command_id='first')
    first = commands.apply_command(tmp_path, **first_args)
    latest = commands.apply_command(tmp_path, operation='test.replay', payload={'topic': 'later'}, expected_head=first['id'], command_id='later')
    assert commands.apply_command(tmp_path, **first_args) == first
    assert calls == ['first', 'later']
    assert store.read_head(tmp_path) == latest


def test_initializer_retry_reestablishes_parent_sync_after_rename(tmp_path, monkeypatch):
    args = dict(command_id='import', state=state(), event=event(), objects={'source': b'original'})
    original = store._fsync_directory
    base = tmp_path / '.researchclaw/research_graph'
    def fail(path):
        if path == base.parent and base.exists():
            raise OSError('parent sync failed')
        original(path)
    monkeypatch.setattr(store, '_fsync_directory', fail)
    with pytest.raises(OSError): store.initialize_record(tmp_path, **args)
    published = store.read_head(tmp_path)
    with pytest.raises(OSError): store.initialize_record(tmp_path, **args)
    synced = []
    def observe(path):
        synced.append(path)
        original(path)
    monkeypatch.setattr(store, '_fsync_directory', observe)
    assert store.initialize_record(tmp_path, **args) == published
    assert base in synced and base.parent in synced
