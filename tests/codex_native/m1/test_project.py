import importlib.util
import multiprocessing
from pathlib import Path

import pytest


def api():
    assert importlib.util.find_spec('researchclaw.core.m1.project') is not None, 'M1 project lifecycle is missing'
    from researchclaw.core.m1.project import init_project
    return init_project


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in root.rglob('*')}


def initialize(root, topic='fixture'):
    return api()(root, topic=topic, profile='materials_ai', max_returns=2)


def test_init_reopen_preserves_state_and_status_is_readonly(tmp_path):
    initial = initialize(tmp_path)
    from researchclaw.core.m1.store import read_head
    assert initial['state']['current_node_id'] == 'scope'
    assert initial['state']['attempts'] == []
    assert initial['state']['returns_used'] == 0
    assert initial['state']['max_returns'] == 2
    assert initial['objects'] == {}
    assert len(initial['events']) == 1
    assert initialize(tmp_path) == initial
    (tmp_path / '.researchclaw/project-transaction.lock').unlink()
    before = snapshot(tmp_path)
    assert read_head(tmp_path) == initial
    assert snapshot(tmp_path) == before
    assert not (tmp_path / '.researchclaw/state.json').exists()


def test_legacy_state_is_not_migrated(tmp_path):
    meta = tmp_path / '.researchclaw'
    meta.mkdir()
    old = meta / 'state.json'
    old.write_text('{"legacy":true}')
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_legacy_project_requires_explicit_migration'):
        initialize(tmp_path)
    assert snapshot(tmp_path) == before
    assert not (meta / 'm1').exists()


def test_nonempty_root_is_preserved(tmp_path):
    (tmp_path / 'notes').write_text('preserve')
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_project_root_not_empty'):
        initialize(tmp_path)
    assert snapshot(tmp_path) == before


def test_conflicting_reopen_does_not_mutate(tmp_path):
    initialize(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_project_config_conflict'):
        initialize(tmp_path, topic='different')
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('options', [dict(topic=''), dict(profile='unknown'), dict(max_returns=-1), dict(max_returns=True)])
def test_invalid_config_has_no_filesystem_side_effects(tmp_path, options):
    kwargs = dict(topic='fixture', profile='materials_ai', max_returns=2)
    kwargs.update(options)
    with pytest.raises(ValueError):
        api()(tmp_path, **kwargs)
    assert not list(tmp_path.iterdir())


def test_relative_root_is_supported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    head = initialize(Path('normal') / 'research')
    from researchclaw.core.m1.store import read_head
    assert read_head(Path('normal/research')) == head


@pytest.mark.parametrize('suffix', ['', '/child', '/../other'])
def test_symlink_root_or_parent_is_rejected(tmp_path, suffix):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    before = snapshot(real)
    with pytest.raises(ValueError, match='m1_path_invalid'):
        initialize(Path(str(link) + suffix))
    assert snapshot(real) == before


def _init_worker(root, barrier, queue):
    barrier.wait(timeout=10)
    try:
        queue.put(('ok', initialize(Path(root))))
    except Exception as exc:
        queue.put(('error', str(exc)))


def test_concurrent_initializers_publish_one_project(tmp_path):
    api()
    ctx = multiprocessing.get_context('spawn')
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    workers = [ctx.Process(target=_init_worker, args=(str(tmp_path), barrier, queue)) for _ in range(2)]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    assert [result[0] for result in results] == ['ok', 'ok']
    assert results[0][1] == results[1][1]


@pytest.mark.parametrize('after_publish', [False, True])
def test_initialization_crash_can_be_reopened(tmp_path, monkeypatch, after_publish):
    api()
    from researchclaw.core.m1 import store
    original = store.os.replace
    def fail_at_publish(source, destination):
        if Path(destination).name == 'm1':
            if after_publish:
                original(source, destination)
            raise OSError('simulated init crash')
        return original(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(store.os, 'replace', fail_at_publish)
        with pytest.raises(OSError, match='simulated init crash'):
            initialize(tmp_path)
    reopened = initialize(tmp_path)
    assert reopened == initialize(tmp_path)
    assert len(reopened['events']) == 1


def test_synthetic_origin_is_explicit_and_conflicting_reopen_is_rejected(tmp_path):
    init_project = api()
    head = init_project(tmp_path, topic='fixture', profile='materials_ai', max_returns=2, content_origin='synthetic')
    assert head['state']['content_origin'] == 'synthetic'
    with pytest.raises(ValueError, match='m1_project_config_conflict'):
        initialize(tmp_path)


def test_initializer_accepts_another_publish_between_existence_and_empty_check(tmp_path, monkeypatch):
    api()
    from researchclaw.core.m1 import project
    original = project._check_new_root
    published = []
    def race(root):
        if not published:
            with monkeypatch.context() as patch:
                patch.setattr(project, '_check_new_root', original)
                published.append(initialize(root))
        return original(root)
    monkeypatch.setattr(project, '_check_new_root', race)
    assert initialize(tmp_path) == published[0]


def test_reopen_reestablishes_durability_after_init_parent_fsync_failure(tmp_path, monkeypatch):
    api()
    from researchclaw.core.m1 import store
    original = store._fsync_directory
    def fail_metadata_directory(path):
        if Path(path) == tmp_path / '.researchclaw':
            raise OSError('init parent fsync failed')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(store, '_fsync_directory', fail_metadata_directory)
        with pytest.raises(OSError, match='init parent fsync failed'):
            initialize(tmp_path)
        visible = store.read_head(tmp_path)
        assert len(visible['events']) == 1
        with pytest.raises(OSError, match='init parent fsync failed'):
            initialize(tmp_path)
        assert store.read_head(tmp_path) == visible
    assert initialize(tmp_path) == visible


@pytest.mark.parametrize('parent_suffix', ['', 'parent', 'parent/project'])
def test_init_retries_parent_sync_for_directories_left_by_failed_creation(tmp_path, monkeypatch, parent_suffix):
    api()
    from researchclaw.core.m1 import store
    root = tmp_path / 'parent/project'
    failed_parent = tmp_path / parent_suffix
    original = store._fsync_directory
    def fail_created_directory_parent(path):
        if Path(path) == failed_parent:
            raise OSError('created directory parent sync failed')
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(store, '_fsync_directory', fail_created_directory_parent)
        with pytest.raises(OSError, match='created directory parent sync failed'):
            initialize(root)
        with pytest.raises(OSError, match='created directory parent sync failed'):
            initialize(root)
        assert not (root / '.researchclaw/m1').exists()
    assert initialize(root) == initialize(root)
