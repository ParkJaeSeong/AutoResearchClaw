"""Discovery projection must never promote private partial rounds or raw telemetry."""
import importlib
import json
import threading

import pytest

from researchclaw.codex.cli import main
from researchclaw.core.research_graph import commands, store
from tests.codex_native.research_graph.test_viewer import fetch


def api():
    return importlib.import_module('researchclaw.codex.discovery_view')


def write(root, name, value):
    (root / name).write_text(json.dumps(value))


def report(role, round=1):
    return dict(role=role, round=round, summary='Public finding', sources=[dict(
        title='Study', doi='10.1234/ABC', url='https://example.org/study', finding='Association',
        limitations='Not causal', raw='PRIVATE')], gaps=['Unresolved'], disagreements=['Alternative'],
        queries=['study'], next_queries=['replication'], sufficient=False,
        observed={'web_calls': 4, 'host_id': 'PRIVATE'}, prompt='PRIVATE')


@pytest.fixture
def data(tmp_path):
    project = tmp_path / 'project'
    commands.init_project(project, topic='Polymers', content_origin='real')
    root = tmp_path / 'discovery'; root.mkdir()
    write(root, 'run.json', {'topic': 'Polymers', 'max_rounds': 3, 'resumed_from': '/PRIVATE'})
    write(root, 'status.json', {'status': 'running', 'round': 2, 'unique_candidates': 9999,
                              'gaps': ['PRIVATE'], 'm1_complete': True})
    reports = [report(role) for role in ('domain', 'methodology', 'critical')]
    reports.append({**report('domain', 2), 'summary': 'PRIVATE'})
    write(root, 'reports.json', reports)
    write(root, 'sources.json', [{'title': 'PRIVATE'}])
    return project, root


def test_complete_round_only_recomputed_candidates_and_no_mutation(data):
    project, root = data
    before = {p: p.read_bytes() for p in project.parent.rglob('*') if p.is_file()}
    result = api().build_discovery_view(project, root)
    assert result['completed_reports'] == 3
    assert result['unique_candidates'] == 1 and result['candidate_records'] == 3
    assert result['sources'][0]['key'] == 'doi:10.1234/abc'
    assert len(result['sources'][0]['observations']) == 3
    assert result['m1_complete'] is False
    assert 'PRIVATE' not in json.dumps(result)
    assert {p: p.read_bytes() for p in project.parent.rglob('*') if p.is_file()} == before


def test_revision_changes_without_native_head_and_selection_is_filtered(data):
    project, root = data
    first = api().build_discovery_view(project, root); head = store.read_head(project)['id']
    write(root, 'selection.json', {'status': 'draft', 'summary': 'Provisional',
        'groups': [{'id': 'g', 'title': 'Core', 'reason': 'Relevant',
                    'source_keys': ['doi:10.1234/abc', 'PRIVATE'], 'prompt': 'PRIVATE'}],
        'hypotheses': [{'id': 'h', 'statement': 'Hypothesis', 'test': 'Compare', 'limits': 'Unknown'}],
        'unresolved': ['Budget'], 'raw': 'PRIVATE'})
    second = api().build_discovery_view(project, root)
    assert first['revision'] != second['revision'] and store.read_head(project)['id'] == head
    assert second['selection']['groups'][0]['source_keys'] == ['doi:10.1234/abc']
    assert 'PRIVATE' not in json.dumps(second)


def test_topic_mismatch_and_symlink_refused(data):
    project, root = data
    write(root, 'run.json', {'topic': 'Other', 'max_rounds': 3})
    with pytest.raises(ValueError, match='topic'):
        api().build_discovery_view(project, root)
    write(root, 'run.json', {'topic': 'Polymers', 'max_rounds': 3})
    (root / 'reports.json').unlink(); (root / 'reports.json').symlink_to(root / 'status.json')
    with pytest.raises(ValueError, match='path'):
        api().build_discovery_view(project, root)


def test_duplicate_role_cannot_release_round(data):
    project, root = data
    write(root, 'reports.json', [report('domain'), report('domain'), report('critical')])
    assert api().build_discovery_view(project, root)['reports'] == []


def test_endpoint_is_explicit_latest_only_and_cli_passes_root(data, monkeypatch):
    from researchclaw.codex import research_viewer
    project, root = data
    server = research_viewer._make_server(project, host='127.0.0.1', port=0, discovery_root=root)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        assert json.loads(fetch(server, '/api/discovery')[1])['unique_candidates'] == 1
        for query in ('root=/tmp', 'head=' + store.read_head(project)['id']):
            assert fetch(server, '/api/discovery?' + query)[0] == 400
        assert fetch(server, '/api/discovery', 'POST')[0] == 405
    finally:
        server.shutdown(); server.server_close(); thread.join()
    calls = []
    monkeypatch.setattr(research_viewer, 'serve_view', lambda *a, **kw: calls.append(kw))
    assert main(['research', 'view', str(project), '--discovery-root', str(root)]) == 0
    assert calls[0]['discovery_root'] == root
    assert api().build_discovery_view(project, None)['available'] is False


def test_url_path_case_is_preserved_and_invalid_selection_fails_closed(data):
    project, root = data
    reports = [report(role) for role in ('domain', 'methodology', 'critical')]
    for item in reports:
        item['sources'][0].update(doi=None, url='https://example.org/Study/')
    write(root, 'reports.json', reports)
    assert api().build_discovery_view(project, root)['sources'][0]['key'] == 'url:https://example.org/Study'
    write(root, 'selection.json', {'groups': None})
    with pytest.raises(ValueError, match='selection'):
        api().build_discovery_view(project, root)


def test_progress_revision_updates_and_does_not_attribute_prior_round_calls(data):
    project, root = data
    first = api().build_discovery_view(project, root)
    role = next(item for item in first['roles'] if item['role'] == 'domain')
    assert role['round'] == 2 and role['web_calls'] == 0
    activity = root / 'round-2-domain'; activity.mkdir()
    write(activity, 'activity.json', {'status': 'running', 'checked_at': '2026-09-10T12:00:00Z',
                                     'prompt': 'PRIVATE', 'web_calls': 999})
    updated = api().build_discovery_view(project, root)
    assert first['revision'] != updated['revision']
    role = next(item for item in updated['roles'] if item['role'] == 'domain')
    assert role['status'] == 'running' and role['last_activity_at'] == '2026-09-10T12:00:00Z'
    assert updated['reports'] == first['reports'] and 'PRIVATE' not in json.dumps(updated)


def test_failed_run_infers_round_and_discloses_only_role_status(data):
    project, root = data
    write(root, 'status.json', {'status': 'failed', 'error': 'PRIVATE'})
    # Round2 domain report is in reports.json, but its peers did not finish.
    activity = root / 'round-2-methodology'; activity.mkdir()
    write(activity, 'activity.json', {'status': 'exited', 'returncode': 1,
                                     'checked_at': '2026-09-10T12:00:00Z', 'error': 'PRIVATE'})
    result = api().build_discovery_view(project, root)
    assert result['round'] == 2
    assert {r['role']: r['status'] for r in result['roles']} == {
        'domain': 'complete', 'methodology': 'failed', 'critical': 'pending'}
    assert result['completed_reports'] == 3 and 'PRIVATE' not in json.dumps(result)


def test_activity_only_round_inference_is_bounded_by_run_and_safe_names(data):
    project, root = data
    write(root, 'status.json', {'status': 'failed'})
    write(root, 'reports.json', [])
    for name in ('round-3-critical', 'round-99-domain', 'round-4-private'):
        path = root / name; path.mkdir()
        write(path, 'activity.json', {'status': 'exited', 'returncode': 2, 'error': 'PRIVATE'})
    result = api().build_discovery_view(project, root)
    assert result['round'] == 3
    assert next(r for r in result['roles'] if r['role'] == 'critical')['status'] == 'failed'
    assert result['reports'] == [] and 'PRIVATE' not in json.dumps(result)
