import errno
import importlib.util
import json
import multiprocessing
from pathlib import Path

import pytest

from tests.codex_native.m1.test_project import initialize, snapshot


def api():
    assert importlib.util.find_spec('researchclaw.core.m1.store') is not None, 'M1 durable store is missing'
    from researchclaw.core.m1 import store
    return store


def event(kind='fixture'):
    return {'schema_version': 1, 'workflow_version': 'm1-graph-v1', 'type': kind, 'payload': {}}


def command(root, head, command_id='cmd-1', **overrides):
    kwargs = dict(expected_head=head['id'], command_id=command_id,
                  state={**head['state'], 'fixture_value': 1}, event=event(), objects={'notes.txt': b'abc'})
    kwargs.update(overrides)
    return api().commit_record(root, **kwargs)


def test_commit_roundtrip_preserves_objects_events_and_extensible_state(tmp_path):
    store = api()
    initial = initialize(tmp_path)
    first = command(tmp_path, initial)
    second = command(tmp_path, first, 'cmd-2', objects={'other.txt': b'def'}, event=event('second'))
    assert store.read_head(tmp_path) == second
    assert [e['type'] for e in second['events']] == ['project_initialized', 'fixture', 'second']
    assert second['state']['fixture_value'] == 1
    digest = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    assert second['objects'][digest] == {'sha256': digest, 'size': 3}
    assert len(second['objects']) == 2
    assert (tmp_path / '.researchclaw/m1/objects' / digest).read_bytes() == b'abc'


def test_idempotence_precedes_head_precondition_and_returns_original_receipt(tmp_path):
    api()
    initial = initialize(tmp_path)
    first = command(tmp_path, initial)
    second = command(tmp_path, first, 'cmd-2')
    before = snapshot(tmp_path)
    assert command(tmp_path, initial) == first
    assert command(tmp_path, initial, expected_head=second['id']) == first
    assert snapshot(tmp_path) == before
    assert api().read_head(tmp_path) == second


@pytest.mark.parametrize('change', [dict(state={'different': True}), dict(event=event('changed')), dict(objects={'notes.txt': b'changed'})])
def test_command_conflict_precedes_stale_head(tmp_path, change):
    api()
    initial = initialize(tmp_path)
    command(tmp_path, initial)
    with pytest.raises(ValueError, match='m1_command_conflict'):
        command(tmp_path, initial, **change)


def test_different_command_cannot_overwrite_stale_head(tmp_path):
    api()
    initial = initialize(tmp_path)
    first = command(tmp_path, initial)
    with pytest.raises(ValueError, match='m1_head_conflict'):
        command(tmp_path, initial, 'other')
    assert api().read_head(tmp_path) == first


@pytest.mark.parametrize('after_publish', [False, True])
def test_crash_at_head_publication_is_atomic_and_retryable(tmp_path, monkeypatch, after_publish):
    store = api()
    initial = initialize(tmp_path)
    original = store.os.replace
    def fail_at_head(source, destination):
        if Path(destination).name == 'HEAD.json':
            if after_publish:
                original(source, destination)
            raise OSError('simulated crash')
        return original(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(store.os, 'replace', fail_at_head)
        with pytest.raises(OSError, match='simulated crash'):
            command(tmp_path, initial)
    current = store.read_head(tmp_path)
    assert len(current['events']) == (2 if after_publish else 1)
    result = command(tmp_path, initial)
    assert len(result['events']) == 2
    assert store.read_head(tmp_path) == result


def test_unpublished_commit_is_not_a_command_receipt(tmp_path, monkeypatch):
    store = api()
    initial = initialize(tmp_path)
    original = store.os.replace
    def stop(source, destination):
        if Path(destination).name == 'HEAD.json':
            raise OSError('crash')
        return original(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(store.os, 'replace', stop)
        with pytest.raises(OSError):
            command(tmp_path, initial)
    other = command(tmp_path, initial, 'other', event=event('other'))
    with pytest.raises(ValueError, match='m1_head_conflict'):
        command(tmp_path, initial)
    result = command(tmp_path, initial, expected_head=other['id'])
    assert [e['type'] for e in result['events']] == ['project_initialized', 'other', 'fixture']


@pytest.mark.parametrize('target', ['head', 'commit', 'object', 'history'])
def test_corrupt_committed_data_fails_without_repair(tmp_path, target):
    store = api()
    initial = initialize(tmp_path)
    head = command(tmp_path, initial)
    base = tmp_path / '.researchclaw/m1'
    path = {'head': base / 'HEAD.json', 'commit': base / 'commits' / head['id'] / 'record.json',
            'object': base / 'objects' / next(iter(head['objects'])),
            'history': base / 'commits' / initial['id'] / 'record.json'}[target]
    path.write_bytes(b'broken')
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_store_corrupt'):
        store.read_head(tmp_path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('location', ['.researchclaw', '.researchclaw/m1', '.researchclaw/m1/objects', '.researchclaw/m1/commits', '.researchclaw/m1/HEAD.json'])
def test_symlink_metadata_paths_are_rejected(tmp_path, location):
    store = api()
    initialize(tmp_path)
    path = tmp_path / location
    moved = tmp_path / 'moved'
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises(ValueError, match='m1_path_invalid'):
        store.read_head(tmp_path)


def test_symlink_object_is_rejected(tmp_path):
    store = api()
    initial = initialize(tmp_path)
    head = command(tmp_path, initial)
    path = tmp_path / '.researchclaw/m1/objects' / next(iter(head['objects']))
    moved = tmp_path / 'moved'
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ValueError, match='m1_path_invalid'):
        store.read_head(tmp_path)


@pytest.mark.parametrize('changes', [dict(command_id=''), dict(event={'unknown': 1}), dict(event={**event(), 'extra': 1}), dict(event={**event(), 'schema_version': 2}), dict(state={'bad': float('nan')}), dict(objects={'../escape': b'x'}), dict(objects={'file': 'not bytes'})])
def test_invalid_command_does_not_change_project(tmp_path, changes):
    api()
    initial = initialize(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        command(tmp_path, initial, **changes)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('failure', ['write', 'file_fsync', 'directory_fsync', 'directory_open'])
def test_disk_errors_propagate_without_partial_head(tmp_path, monkeypatch, failure):
    store = api()
    initial = initialize(tmp_path)
    import stat
    original_open, original_fsync = store.os.open, store.os.fsync
    def failing_open(path, flags, *args, **kwargs):
        if (failure == 'write' and flags & store.os.O_WRONLY) or (failure == 'directory_open' and Path(path).name == 'objects'):
            raise OSError(errno.ENOSPC, 'disk full')
        return original_open(path, flags, *args, **kwargs)
    def failing_fsync(fd):
        is_dir = stat.S_ISDIR(store.os.fstat(fd).st_mode)
        if failure == ('directory_fsync' if is_dir else 'file_fsync'):
            raise OSError(errno.ENOSPC, 'disk full')
        return original_fsync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(store.os, 'open', failing_open)
        patch.setattr(store.os, 'fsync', failing_fsync)
        with pytest.raises(OSError) as caught:
            command(tmp_path, initial)
        assert caught.value.errno == errno.ENOSPC
    assert store.read_head(tmp_path) == initial


def _commit_worker(root, head, command_id, barrier, queue):
    barrier.wait(timeout=10)
    try:
        queue.put(('ok', command(Path(root), head, command_id)))
    except ValueError as exc:
        queue.put(('error', str(exc)))


@pytest.mark.parametrize('same_command', [False, True])
def test_concurrent_writers_are_serialized(tmp_path, same_command):
    api()
    initial = initialize(tmp_path)
    ctx = multiprocessing.get_context('spawn')
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    workers = [ctx.Process(target=_commit_worker, args=(str(tmp_path), initial, 'same' if same_command else str(i), barrier, queue)) for i in range(2)]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    if same_command:
        assert results[0] == results[1]
        assert results[0][0] == 'ok'
    else:
        assert sorted(result[0] for result in results) == ['error', 'ok']
        assert next(result[1] for result in results if result[0] == 'error') == 'm1_head_conflict'
    assert len(api().read_head(tmp_path)['events']) == 2


@pytest.mark.parametrize('change', [dict(extra=True), dict(schema_version=True), dict(schema_version=2), dict(workflow_version='legacy'), dict(id='../escape')])
def test_head_envelope_is_closed_and_versioned(tmp_path, change):
    store = api()
    initialize(tmp_path)
    path = tmp_path / '.researchclaw/m1/HEAD.json'
    envelope = json.loads(path.read_text())
    envelope.update(change)
    path.write_text(json.dumps(envelope))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_store_corrupt'):
        store.read_head(tmp_path)
    assert snapshot(tmp_path) == before


def test_retry_reestablishes_durability_after_head_fsync_failure(tmp_path, monkeypatch):
    store = api()
    initial = initialize(tmp_path)
    original = store._fsync_directory
    def fail_head_directory(path):
        if Path(path) == tmp_path / '.researchclaw/m1':
            raise OSError(errno.EIO, 'HEAD directory fsync failed')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(store, '_fsync_directory', fail_head_directory)
        with pytest.raises(OSError, match='HEAD directory fsync failed'):
            command(tmp_path, initial)
        visible = store.read_head(tmp_path)
        assert len(visible['events']) == 2
        with pytest.raises(OSError, match='HEAD directory fsync failed'):
            command(tmp_path, initial)
        assert store.read_head(tmp_path) == visible
    assert command(tmp_path, initial) == visible


def test_fresh_commit_reestablishes_failed_init_publication_durability(tmp_path, monkeypatch):
    store = api()
    original = store._fsync_directory
    def fail_metadata_directory(path):
        if Path(path) == tmp_path / '.researchclaw':
            raise OSError(errno.EIO, 'init publication parent sync failed')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(store, '_fsync_directory', fail_metadata_directory)
        with pytest.raises(OSError, match='init publication parent sync failed'):
            initialize(tmp_path)
        initial = store.read_head(tmp_path)
        with pytest.raises(OSError, match='init publication parent sync failed'):
            command(tmp_path, initial)
        current = store.read_head(tmp_path)
        assert len(current['events']) == 2
        with pytest.raises(OSError, match='init publication parent sync failed'):
            command(tmp_path, initial)
        assert store.read_head(tmp_path) == current
    assert command(tmp_path, initial) == current
    later = command(tmp_path, current, 'later-command')
    assert command(tmp_path, initial) == current
    assert store.read_head(tmp_path) == later
