"""Registered snapshot views: exact lineage, disclosure and read-only semantics."""
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.council import prepare_council
from researchclaw.core.m1.packets import register_outputs
from tests.codex_native.m1.helpers import build_review_case, encoded, submission
from tests.codex_native.m1.test_assignments import assignments
from tests.codex_native.m1.test_budgets import apply, plan, change_state
from tests.codex_native.m1.test_council import submit
from tests.codex_native.m1.test_project import snapshot


def api():
    assert importlib.util.find_spec('researchclaw.core.m1.views'), 'M1 read-only view is missing'
    return importlib.import_module('researchclaw.core.m1.views')


@pytest.fixture(scope='module')
def history_base(tmp_path_factory):
    root = tmp_path_factory.mktemp('view-history')
    build_review_case(root, outcome='return_hypothesis')
    old = store.read_head(root)
    applied = apply(root, plan(root))
    packet = applied['packet']
    ref = next(r for r in old['state']['artifacts'] if r['logical_path'] == 'hypotheses/hypotheses.json')
    h1 = json.loads(store._read_file(store._store_path(root) / 'objects' / ref['sha256']))['hypotheses'][0]
    h2 = {**h1, 'revision': 2, 'parent_revision': 1, 'statement': 'Registered narrowed comparison.',
          'change_reason': 'The recorded critique limits the interpretation.'}
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, {
        'hypotheses/hypotheses.json': encoded({'schema_version': 1, 'hypotheses': [h1, h2]}),
        'hypotheses/hypotheses.md': b'Recorded narrowed comparison.'}), command_id='r2')
    assert result['status'] == 'review_pending'
    session = prepare_council(root, attempt_id=applied['attempt']['id'], assignments=assignments(), command_id='review2')['session']
    submit(root, session, 'A1', command_id='r2-first', rationale=['PRIVATE INITIAL SENTINEL'])
    return root, old['id'], session


@pytest.fixture
def case(tmp_path, history_base):
    root, old, session = history_base
    target = tmp_path / 'project'
    shutil.copytree(root, target)
    return target, old, session


def test_decision_lookup_preserves_dissent():
    decision = {'id': 'D1', 'dissent': ['scope is limited']}
    assert api().find_decision({'decisions': [decision]}, 'D1') == decision
    assert api().find_decision({'decisions': [decision]}, 'D2') is None


def test_latest_and_historical_links_are_exact_and_read_only(case):
    root, old, _ = case
    before = snapshot(root)
    latest = api().build_view(root)
    historical = api().build_view(root, head_id=old)
    assert snapshot(root) == before
    assert historical['head_id'] == old != latest['head_id']
    assert len(historical['sessions']) == 1 and len(latest['sessions']) == 2
    assert historical['budget']['returns_used'] == 0 and latest['budget']['returns_used'] == 1
    assert historical['next_actions'][0]['action'] == 'plan_return'
    assert latest['next_actions'][0]['action'] == 'collect_initials'
    assert historical['transitions'] == [] and latest['return_context']['to_attempt_id']
    for view in (historical, latest):
        decision = api().find_decision(view, 'synthetic-decision')
        issues = {v['id']: v for v in view['issues']}
        responses = {v['id']: v for v in view['responses']}
        artifacts = {v['id']: v for v in view['artifacts']}
        assert decision['issue_ids'] and all(i in issues for i in decision['issue_ids'])
        assert decision['response_ids'] and all(i in responses for i in decision['response_ids'])
        assert all(r['issue_id'] in issues for r in responses.values())
        assert all(i in artifacts for i in decision['evidence_refs'])
        assert all(i in artifacts for i in decision['hypothesis_versions'])
        assert decision['dissent'][0]['rationale']
        assert not view['missing_references']
        assert view['data_origin'] == 'registered' and view['content_origin'] == 'synthetic'
        assert decision['provenance_status'] == 'declared_only'
    old_decision = historical['decisions'][0]
    assert {a['revision'] for a in historical['artifacts'] if a['kind'] == 'hypothesis'} == {1}
    new_decision = latest['decisions'][0]
    projected = {a['id']: a for a in latest['artifacts']}
    assert [projected[i]['revision'] for i in new_decision['hypothesis_versions']] == [1, 2]
    assert old_decision['hypothesis_versions'][0] == new_decision['hypothesis_versions'][0]
    child = projected[new_decision['hypothesis_versions'][1]]
    assert child['parent_revision'] == 1 and child['change_reason']
    assert child['registered'] is False and child['projection'] is True
    assert projected[child['source_artifact_id']]['sha256'] == child['source_artifact_sha256']


def test_pending_initial_is_absent_everywhere_but_submission_status_visible(case):
    root, _, session = case
    view = api().build_view(root)
    assert 'PRIVATE INITIAL SENTINEL' not in json.dumps(view)
    pending = next(s for s in view['sessions'] if s['id'] == session['id'])
    assert pending['disclosed_initials'] == []
    assert {a['id']: a['initial_status'] for a in pending['assignments']} == {'A1': 'submitted', 'A2': 'waiting', 'A3': 'waiting'}
    assert 'events' not in view and 'objects' not in view and 'receipt' not in view
    assert all(i['session_id'] != session['id'] for i in view['issues'])
    hidden = store.read_head(root)['state']['sessions'][session['id']]['initials']['A1']
    assert hidden['submission_sha256'] not in json.dumps(view)
    assert store._hash(store._canonical(hidden)) not in json.dumps(view)


def test_scoped_issue_ids_never_cross_sessions(case):
    root, _, session = case
    old = next(s for s in store.read_head(root)['state']['sessions'].values() if s['id'] != session['id'])
    original = next(issue for position in old['disclosed_initials'] for issue in position['open_issues'])
    issue = {k: deepcopy(v) for k, v in original.items() if k != 'session_id'}
    issue.update(raised_by='A2', target_refs=[{'id': 'H1', 'revision': 2}],
                 evidence_refs=[session['input_refs'][0]['id']])
    submit(root, session, 'A2', command_id='r2-second', open_issues=[issue])
    submit(root, session, 'A3', command_id='r2-third')
    view = api().build_view(root)
    matches = [i for i in view['issues'] if i['original_id'] == original['id']]
    assert len(matches) == 2 and len({i['id'] for i in matches}) == 2
    for issue in matches:
        assert issue['session_id'] in issue['id']
        assert all(r['session_id'] == issue['session_id'] for r in view['responses'] if r['issue_id'] == issue['id'])
    assert 'PRIVATE INITIAL SENTINEL' in json.dumps(view)
    from tests.codex_native.m1.test_issues import register_response, response_payload
    original_response = old['disclosed_responses'][0]['responses'][0]
    reply = {**original_response, 'assignment_id': 'A1', 'evidence_refs': []}
    for reviewer in ('A1', 'A2', 'A3'):
        register_response(root, session, reviewer, command_id='second-response-' + reviewer,
                          payload=response_payload(session, reviewer, responses=[reply] if reviewer == 'A1' else []))
    view = api().build_view(root)
    repeated = [r for r in view['responses'] if r['original_id'] == original_response['id']]
    assert len(repeated) == 2 and len({r['id'] for r in repeated}) == 2
    assert len({r['issue_id'] for r in repeated}) == 2
    for reply in repeated:
        issue = next(i for i in view['issues'] if i['id'] == reply['issue_id'])
        assert issue['session_id'] == reply['session_id']


def test_one_verified_ancestry_and_no_current_head_helpers(case, monkeypatch):
    root, old, _ = case
    original = store._history
    calls = []
    def history(base):
        calls.append(base)
        return original(base)
    monkeypatch.setattr(store, '_history', history)
    monkeypatch.setattr(store, 'read_head', lambda *_: pytest.fail('mixed HEAD read'))
    view = api().build_view(root, head_id=old)
    assert view['head_id'] == old and len(calls) == 1


@pytest.mark.parametrize('head_id', ['bad', '0' * 64])
def test_unknown_or_unreachable_head_rejected(case, head_id):
    root, _, _ = case
    before = snapshot(root)
    with pytest.raises(ValueError, match='m1_view_head_not_reachable'):
        api().build_view(root, head_id=head_id)
    assert snapshot(root) == before


def test_missing_exact_artifact_is_reported_not_replaced(case):
    root, _, _ = case
    old_ref = next(r for r in store.read_head(root)['state']['artifacts'] if r['logical_path'] == 'hypotheses/hypotheses.json')
    change_state(root, lambda state: state['artifacts'].remove(old_ref))
    view = api().build_view(root)
    assert any(m['reference_id'] == old_ref['id'] for m in view['missing_references'])
    assert view['decisions'][0]['hypothesis_versions'] == []


def test_demo_and_registered_share_core_contract(case):
    root, _, _ = case
    demo = json.loads(Path('tests/ui/m1/demo.json').read_text())
    for view in (demo, api().build_view(root)):
        api().validate_view(view)
    with pytest.raises(ValueError, match='m1_view_invalid'):
        api().validate_view({**demo, 'issues': {}})


def test_inspect_cli_supports_selected_head(case, capsys):
    from researchclaw.codex.cli import main
    root, old, _ = case
    before = snapshot(root)
    assert main(['m1', 'inspect', str(root), '--head', old, '--json']) == 0
    output = capsys.readouterr()
    assert output.err == '' and json.loads(output.out)['head_id'] == old
    assert snapshot(root) == before


def test_snapshot_reuses_each_verified_artifact_body(case, monkeypatch):
    root, _, _ = case
    counts = {}
    original = store._read_file
    def read(path):
        if path.parent.name == 'objects':
            counts[path.name] = counts.get(path.name, 0) + 1
        return original(path)
    monkeypatch.setattr(store, '_read_file', read)
    api().build_view(root)
    # One integrity traversal read, at most one cached projection read.
    assert max(counts.values()) <= 2


def test_historical_approval_and_budget_do_not_follow_current_root(case):
    from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
    from researchclaw.core.m1.budgets import set_return_budget
    root, old, _ = case
    record_corpus_approval(root, corpus_binding=current_corpus(root)['corpus_binding'], decision='reject',
                          note='Explicit later revocation', command_id='later-revoke')
    set_return_budget(root, limit=0, note='Explicit later stop', command_id='later-budget')
    latest = api().build_view(root)
    historical = api().build_view(root, head_id=old)
    assert latest['next_actions'][0]['action'] == 'await_user'
    assert 'm1_corpus_approval_required' in latest['wait_reasons']
    assert latest['budget']['exhausted']
    assert historical['next_actions'][0]['action'] == 'plan_return'
    assert historical['budget']['max_returns'] == 2
    assert historical['approvals'][-1]['decision'] == 'approve'


def test_replaced_or_failed_pending_initials_and_orphan_objects_never_publish(case):
    from researchclaw.core.m1.council import replace_assignment
    root, _, session = case
    replace_assignment(root, session_id=session['id'], assignment_id='A1',
                       replacement={'id': 'new-A1', 'role_id': 'domain', 'host_task_id': 'new-host'},
                       reason='Caller reported interrupted role', command_id='replace')
    change_state(root, lambda state: state['sessions'][session['id']].update(status='role_failed'))
    view = api().build_view(root)
    assert 'PRIVATE INITIAL SENTINEL' not in json.dumps(view)
    failed = next(s for s in view['sessions'] if s['id'] == session['id'])
    assert failed['assignment_history'][0]['reason'] == 'Caller reported interrupted role'
    assert 'initial' not in failed['assignment_history'][0]
    assert view['next_actions'][0]['action'] == 'await_user'
    assert view['wait_reasons']


def test_real_orphan_commit_is_not_a_selectable_historical_head(case):
    root, _, _ = case
    head_path = store._store_path(root) / 'HEAD.json'
    before = head_path.read_bytes()
    change_state(root, lambda state: state.update(topic='UNPUBLISHED ORPHAN SENTINEL'))
    orphan = store.read_head(root)['id']
    head_path.write_bytes(before)  # Simulate an orphan left before HEAD publication.
    with pytest.raises(ValueError, match='m1_view_head_not_reachable'):
        api().build_view(root, head_id=orphan)
    assert 'UNPUBLISHED ORPHAN SENTINEL' not in json.dumps(api().build_view(root))


def test_frozen_role_narratives_and_nested_references_preserved(case):
    root, old, _ = case
    view = api().build_view(root, head_id=old)
    decision = view['decisions'][0]
    original = store.read_head(root)['state']['decisions'][0]
    for projected, native in zip(decision['positions'], original['positions']):
        for key in ('assignment_id', 'role_id', 'host_task_id', 'rationale', 'change_rationale', 'recommendation', 'evidence_refs', 'provenance_status'):
            assert projected[key] == native[key]
        assert all(d['issue_id'] in decision['issue_ids'] for d in projected['issue_dispositions'])
        assert all(r in decision['response_ids'] for d in projected['issue_dispositions'] for r in d['response_ids'])
    assert [p['rationale'] for p in decision['dissent']] == [p['rationale'] for p in original['dissent']]
    assert decision['rationale'] == original['rationale']
    assert decision['limitations'] == original['limitations']


def test_preview_is_bounded_exact_text_and_read_only(tmp_path):
    from researchclaw.core.m1.project import init_project
    from researchclaw.core.m1.packets import prepare_node
    init_project(tmp_path, topic='Authored topic', profile='materials_ai', max_returns=2)
    packet = prepare_node(tmp_path, 'scope', command_id='scope')['packet']
    text = '<script>never execute</script>' + '가' * 6000
    result = register_outputs(tmp_path, packet_id=packet['id'], command_id='text', submission=submission(tmp_path, packet, {
        'scope/goal.md': text.encode(), 'scope/constraints.json': b'{}'}))
    assert not result['issues']
    before = snapshot(tmp_path)
    view = api().build_view(tmp_path)
    artifact = next(a for a in view['artifacts'] if a.get('logical_path') == 'scope/goal.md')
    assert artifact['content'] == text[:api().PREVIEW_CHARACTERS]
    assert artifact['content_truncated'] is True and artifact['content_length'] == len(text)
    assert artifact['registered'] and artifact['sha256']
    assert view['project']['title'] == 'Authored topic'
    assert snapshot(tmp_path) == before


def test_unrelated_latest_hypothesis_never_replaces_decision_lineage(case):
    from tests.codex_native.m1.helpers import checkpoint
    root, _, _ = case
    before = api().build_view(root)['decisions'][0]['hypothesis_versions']
    head = store.read_head(root)
    ref = [r for r in head['state']['artifacts'] if r['logical_path'] == 'hypotheses/hypotheses.json'][-1]
    body = json.loads(store._read_file(store._store_path(root) / 'objects' / ref['sha256']))
    new = {**body['hypotheses'][0], 'revision': 99, 'parent_revision': 1,
           'statement': 'UNRELATED REGISTERED VERSION', 'change_reason': 'Different recorded attempt.'}
    checkpoint(root, node='hypothesize', files={'hypotheses/hypotheses.json': encoded({'schema_version': 1, 'hypotheses': [new]})})
    view = api().build_view(root)
    assert any(a.get('revision') == 99 for a in view['artifacts'])
    assert view['decisions'][0]['hypothesis_versions'] == before
