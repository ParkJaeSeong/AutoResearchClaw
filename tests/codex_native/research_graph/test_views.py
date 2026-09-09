"""U1 public projection boundaries on native commands and immutable ancestry."""
from copy import deepcopy
import importlib
import json
import shutil

import pytest

from researchclaw.core.research_graph import commands, migration, store
from tests.codex_native.research_graph.test_m1_scope import Fixture, uid


def api():
    return importlib.import_module('researchclaw.core.research_graph.views')


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def f(tmp_path):
    fixture = Fixture(tmp_path / 'project'); fixture.register(); fixture.council_prepare()
    return fixture


def test_view_hides_partial_phase_bodies_ids_hashes_and_only_discloses_complete_phase(f):
    first = f.submit(0, 'initial', rationale='PRIVATE first review')
    second = f.submit(1, 'initial', rationale='PRIVATE second review')
    pinned = f.head['id']; before = files(f.root)
    view = api().build_view(f.root)
    text = json.dumps(view)
    for record in (first, second):
        for secret in (record['rationale'], record['id'], record['event_id'], store._hash(store._canonical(record))):
            assert secret not in text
    council = view['councils'][0]
    assert council['phase'] == 'initial' and council['submitted_counts']['initial'] == 2
    assert council['disclosed_initials'] == [] and 'own_submissions' not in council
    assert len(council['participants']) == 3 and council['isolation_level'] == 'instructions_only'
    assert files(f.root) == before
    f.submit(2, 'initial', rationale='Third explicit review')
    view = api().build_view(f.root)
    assert len(view['councils'][0]['disclosed_initials']) == 3
    assert first['rationale'] in json.dumps(view)
    old = api().build_view(f.root, head_id=pinned)
    assert old['head_id'] == pinned and old['current_head_id'] == f.head['id']
    assert first['id'] not in json.dumps(old)
    assert all('state' not in item and 'events' not in item for item in old['heads'])


def test_native_revisions_actual_moves_and_selected_history_keep_original_bytes(f):
    f.complete(); old = f.head['id']; old_ref = f.check()['node_ref']; old_id = f.artifact['id']
    f.register(f.node(previous_ref=old_ref, revision_reason='Clarify user constraints'))
    before = files(f.root); view = api().build_view(f.root)
    assert len(view['revisions']) == 2
    newest = view['revisions'][-1]
    assert newest['previous_ref'] == old_ref and newest['current'] is True
    assert view['nodes'][0]['current_revision_id'] == f.artifact['id']
    assert view['transitions'][-1]['from_node'] == view['transitions'][-1]['to_node'] == 'scope'
    assert api().build_view(f.root, head_id=old)['nodes'][0]['current_revision_id'] == old_id
    assert len(view['nodes']) == 9
    assert view['milestones'][1]['status'] == view['milestones'][2]['status'] == 'unavailable'
    assert files(f.root) == before


def test_orphan_commit_is_not_a_selectable_snapshot(f):
    orphan = store._canonical({'orphan': True}); digest = store._hash(orphan)
    directory = store._store_path(f.root) / 'commits' / digest; directory.mkdir(); (directory / 'record.json').write_bytes(orphan)
    before = files(f.root)
    with pytest.raises(ValueError, match='^research_view_head_unreachable$'):
        api().build_view(f.root, head_id=digest)
    assert files(f.root) == before


def test_raw_is_selected_public_allowlist_not_digest_or_forged_projection(f):
    hidden = f.submit(0, 'initial', rationale='RAW PRIVATE')
    pinned = f.head['id']; view = api().build_view(f.root)
    artifact = next(a for a in view['artifacts'] if a['ref']['artifact_id'] == 'm1/nodes/scope')
    data = api().read_artifact(f.root, artifact_id=artifact['id'], head_id=pinned)
    assert json.loads(data)['content'] == f.artifact['content']
    digest = store._hash(store._canonical(hidden))
    for fake in (digest, hidden['id'], '../HEAD.json', '0' * 64):
        with pytest.raises(ValueError, match='^research_view_artifact_unavailable$'):
            api().read_artifact(f.root, artifact_id=fake, head_id=pinned)
    view['artifacts'].append({'id': digest, 'ref': f.submitted['initial'][0]})
    with pytest.raises(ValueError, match='^research_view_artifact_unavailable$'):
        api().read_artifact(f.root, artifact_id=digest, head_id=pinned)


def test_nested_dependency_and_observation_cannot_launder_private_reference(f):
    hidden = f.submit(0, 'initial', rationale='PRIVATE NESTED')
    ref = f.submitted['initial'][0]
    dependency = {**f.envelope(), 'from_ref': ref, 'to_ref': f.binding, 'relation': 'supports', 'origin_group_id': 'unknown'}
    wrapper = {**f.envelope(), 'verification_id': uid(), 'output_refs': [ref], 'outcome': 'inconclusive',
               'checked_scope': ['Declared'], 'limitations': ['Not a valid private-body route']}
    state = deepcopy(f.head['state']); state.update(dependencies={dependency['id']: dependency}, verification_results={wrapper['id']: wrapper})
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_boundary_fixture', 'payload': {}},
        objects={r['id']: store._canonical(r) for r in (dependency, wrapper)})
    view = api().build_view(f.root); raw = json.dumps(view)
    assert hidden['id'] not in raw and ref['sha256'] not in raw and 'PRIVATE NESTED' not in raw
    assert view['dependencies'] == [] and view['results'] == []
    for artifact in view['artifacts']:
        assert hidden['id'].encode() not in api().read_artifact(f.root, artifact_id=artifact['id'])


def test_imported_issue_projection_is_pending_without_archived_private_raw(tmp_path):
    from tests.codex_native.research_graph.test_migration import source_fixture
    source = tmp_path / 'legacy'; target = tmp_path / 'imported'; selected = source_fixture(source)
    migration.import_m1(source, target, source_head=selected['id'], command_id='import')
    before = files(source); view = api().build_view(target)
    assert len(view['issues']) == 6
    assert all(item['imported_pending'] and item['status'] == 'pending_policy_revalidation' and not item['history'] for item in view['issues'])
    assert 'SECRET' not in json.dumps(view)
    assert not any(a['ref']['artifact_id'].startswith('archive/') for a in view['artifacts'])
    assert files(source) == before


def test_native_issue_timeline_uses_events_not_issue_states_cache(f):
    issue = f.issue(); f.publish(issue)
    state = deepcopy(f.head['state']); state['issue_states'][issue['id']] = 'resolved'
    f.head = store.commit_record(f.root, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_cache_fixture', 'payload': {}}, objects={})
    view = api().build_view(f.root); projected = next(row for row in view['issues'] if row['record']['id'] == issue['id'])
    assert projected['status'] == 'open' and projected['history'][-1]['record']['to_status'] == 'open'
    assert projected['history'][-1]['record']['rationale'] == 'Publish the scoped issue'


def test_build_view_verifies_current_ancestry_once_per_request(f, monkeypatch):
    original = store._history; calls = []
    def read(base):
        calls.append(base); return original(base)
    monkeypatch.setattr(store, '_history', read)
    api().build_view(f.root)
    assert len(calls) == 1


# One cached native prerequisite chain proves the UI consumes real B05/B07
# producers; the small boundary tests above do not rebuild that chain.
from tests.codex_native.research_graph.test_handoffs import (
    accounted_baseline, reviewed_baseline, extracted_baseline, collected_baseline, native_baseline, reload)


def test_complete_native_evidence_approval_and_handoff_projection(accounted_baseline, tmp_path):
    root = tmp_path / 'project'; shutil.copytree(accounted_baseline, root)
    f = reload(root); f.issue_package(); f.receiver(); f.accept()
    before = files(root); view = api().build_view(root)
    assert view['evidence']['ready'] is True and view['corpus']['approved'] is True
    assert view['evidence']['source_groups']['source_count'] == 2
    assert view['evidence']['source_groups']['origin_group_count'] == 1
    assert view['evidence']['limitations'] and view['source_checks'] and view['results'] and view['approvals']
    assert len(view['revisions']) == 9 and all(node['status'] == 'ready' for node in view['nodes'])
    assert view['handoffs'][0]['assessment']['status'] == 'accepted'
    assert view['handoffs'][0]['assessment']['gate_ready'] is True
    assert view['milestones'][1]['status'] == 'unavailable'
    assert any(a['ref']['artifact_id'].startswith('m1/source-text/') for a in view['artifacts'])
    assert files(root) == before
