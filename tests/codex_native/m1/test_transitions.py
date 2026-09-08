"""Read-only return planning from registered synthetic decisions."""
from copy import deepcopy
import importlib
import importlib.util
import json
import shutil

import pytest

from researchclaw.core.m1 import store
from tests.codex_native.m1.helpers import build_review_case, checkpoint
from tests.codex_native.m1.test_decisions import completed, decision_payload, decide


def api():
    name = 'researchclaw.core.m1.transitions'
    assert importlib.util.find_spec(name), 'M1 return planner is missing'
    return importlib.import_module(name)


def test_only_dependent_attempts_are_affected():
    attempts = [
        {'id': 'A2', 'input_refs': ['S1'], 'output_refs': ['H1']},
        {'id': 'A1', 'input_refs': ['C1'], 'output_refs': ['S1']},
        {'id': 'A3', 'input_refs': ['other'], 'output_refs': ['other-out']},
        {'id': 'old-version', 'input_refs': ['C0'], 'output_refs': ['old-out']},
    ]
    original = deepcopy(attempts)
    assert api().affected_attempts(attempts, {'C1'}) == ('A1', 'A2')
    assert attempts == original
    assert api().affected_attempts(attempts, set()) == ()


def test_dependency_cycles_converge_without_inventing_impacts():
    attempts = [{'id': 'A', 'input_refs': ['B-out'], 'output_refs': ['A-out']},
                {'id': 'B', 'input_refs': ['A-out'], 'output_refs': ['B-out']}]
    assert api().affected_attempts(attempts, {'A-out'}) == ('A', 'B')
    assert api().affected_attempts(attempts, {'unrelated'}) == ()


@pytest.fixture(scope='module')
def decision_base(tmp_path_factory):
    root = tmp_path_factory.mktemp('return-base')
    completed(root)
    return root


@pytest.fixture
def case(tmp_path, decision_base):
    root = tmp_path / 'project'
    shutil.copytree(decision_base, root)
    return root


def register_case(root, *, target='hypothesize', work=None):
    session = next(iter(store.read_head(root)['state']['sessions'].values()))
    payload = decision_payload(session)
    payload['return_target'] = target
    if work is not None:
        payload['proposed_work'] = work
    decide(root, session, payload)
    return payload


def plan(root, **kwargs):
    return api().plan_return(root, **{'decision_id': 'decision-one',
        'target_node_id': 'hypothesize', 'issue_ids': ['issue-A1'], **kwargs})


def snapshot(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None)
            for path in [root, *root.rglob('*')]}


def test_hypothesis_plan_reuses_evidence_and_keeps_every_byte_and_mtime(case):
    payload = register_case(case)
    head = store.read_head(case)
    before = snapshot(case)
    result = plan(case)
    attempts = {a['node_id']: a for a in head['state']['attempts']}
    assert result['from_attempt_id'] == attempts['review']['id']
    assert result['affected_attempt_ids'] == sorted([attempts['hypothesize']['id'], attempts['review']['id']])
    assert attempts['collect']['id'] in result['reusable_attempt_ids']
    assert attempts['synthesize']['id'] in result['reusable_attempt_ids']
    assert attempts['hypothesize']['id'] not in result['reusable_attempt_ids']
    assert result['changed_artifact_ids'] == sorted(r['id'] for r in attempts['hypothesize']['output_refs'])
    assert result['rationale'] == payload['rationale']
    assert result['proposed_work'] == payload['proposed_work']
    assert result['reason_code'] == 'hypothesis_revision'
    assert result['approval_effects']['current']['approved'] is True
    assert result['approval_effects']['after_change']['approval_required'] is False
    assert result['approval_effects']['after_change']['approval_id'] == head['state']['approvals'][-1]['id']
    assert result['input_head'] == head['id']
    assert result == plan(case)
    assert snapshot(case) == before
    body = {k: v for k, v in result.items() if k not in ('id', 'plan_hash')}
    assert result['plan_hash'] == store._hash(store._canonical(body))
    assert result['id'] == 'return-' + result['plan_hash']


@pytest.mark.parametrize(('target', 'reason', 'needs_approval', 'affected_nodes'), [
    ('collect', 'source_change', True, {'collect', 'screen', 'extract', 'synthesize', 'hypothesize', 'review'}),
    ('screen', 'corpus_selection_change', True, {'screen', 'extract', 'synthesize', 'hypothesize', 'review'}),
    ('extract', 'extraction_error', False, {'extract', 'synthesize', 'hypothesize', 'review'}),
    ('synthesize', 'synthesis_revision', False, {'synthesize', 'hypothesize', 'review'}),
    ('questions', 'question_change', True, {'questions', 'screen', 'extract', 'synthesize', 'hypothesize', 'review'}),
    ('search', 'search_change', True, {'search', 'extract', 'synthesize', 'hypothesize', 'review'}),
    ('scope', 'scope_change', True, {'scope', 'screen', 'extract', 'synthesize', 'hypothesize', 'review'}),
])
def test_target_impacts_follow_registered_dependencies_not_node_order(case, target, reason, needs_approval, affected_nodes):
    # Upfront fixture attempts intentionally have no input edges. Their graph
    # order is not evidence that they consumed an artifact.
    register_case(case, target=target, work=['Correct the registered evidence for issue-A1.'])
    before = snapshot(case)
    result = plan(case, target_node_id=target)
    attempts = store.read_head(case)['state']['attempts']
    assert {a['node_id'] for a in attempts if a['id'] in result['affected_attempt_ids']} == affected_nodes
    assert result['reason_code'] == reason
    current, after = result['approval_effects']['current'], result['approval_effects']['after_change']
    assert current['approved'] is True
    assert after['approval_required'] is needs_approval
    assert after['screen_required'] is needs_approval
    assert (after['approval_id'] is None) is needs_approval
    assert (after['corpus_binding'] is None) is needs_approval
    assert snapshot(case) == before


@pytest.mark.parametrize('target', ['stage-12', 'M2', 'handoff', 'review', 'extract'])
def test_rejects_m2_and_silent_retargeting(case, target):
    register_case(case)
    before = snapshot(case)
    with pytest.raises(ValueError, match='m1_return_target_invalid'):
        plan(case, target_node_id=target)
    assert snapshot(case) == before


@pytest.mark.parametrize('issues', [[], ['foreign-issue'], ['issue-A1', 'issue-A1'], [None], 'issue-A1'])
def test_issues_must_be_unique_nonempty_ids_from_decision_session(case, issues):
    register_case(case)
    before = snapshot(case)
    with pytest.raises(ValueError, match='m1_return_issue_invalid'):
        plan(case, issue_ids=issues)
    assert snapshot(case) == before


@pytest.mark.parametrize('work', [
    ['reset all'], ['Reset all stages and start over.'], ['전체 초기화'],
    ['Delete the entire project and rebuild every stage.'],
    ['Restart the whole workflow from the beginning.'],
])
def test_blanket_reset_is_not_a_change_plan(case, work):
    register_case(case, target='scope', work=work)
    before = snapshot(case)
    with pytest.raises(ValueError, match='m1_return_work_required'):
        plan(case, target_node_id='scope')
    assert snapshot(case) == before


@pytest.mark.parametrize('work', [
    'Delete all unsupported causal claims from H1 and retain the evidence-backed descriptive prediction.',
    'Redo all predictions in H1 against the registered observation.',
    'Start over with H1 wording while retaining the registered evidence.',
])
def test_scoped_hypothesis_edits_are_not_misread_as_workflow_resets(case, work):
    register_case(case, work=[work])
    before = snapshot(case)
    result = plan(case)
    attempts = store.read_head(case)['state']['attempts']
    assert result['proposed_work'] == [work]
    assert {a['node_id'] for a in attempts if a['id'] in result['affected_attempt_ids']} == {'hypothesize', 'review'}
    assert {a['node_id'] for a in attempts if a['id'] in result['reusable_attempt_ids']} >= {'collect', 'extract', 'synthesize'}
    assert result['approval_effects']['after_change']['approval_required'] is False
    assert snapshot(case) == before


def test_ready_decision_cannot_authorize_return(tmp_path):
    value = build_review_case(tmp_path, outcome='ready')
    with pytest.raises(ValueError, match='m1_return_not_authorized'):
        plan(tmp_path, decision_id=value['decision_id'], issue_ids=['invented'])


@pytest.mark.parametrize('change', ['current_node', 'evidence', 'approval'])
def test_registered_decision_cannot_plan_against_stale_review(case, change):
    from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
    register_case(case)
    if change == 'current_node':
        checkpoint(case, node='hypothesize')
    elif change == 'evidence':
        checkpoint(case, files={'knowledge/synthesis.json': b'{}'})
    else:
        record_corpus_approval(case, corpus_binding=current_corpus(case)['corpus_binding'],
                              decision='reject', note='Revoked test approval', command_id='revoke')
    before = snapshot(case)
    with pytest.raises(ValueError, match='m1_council_stale|m1_council_input_changed|m1_corpus_approval_required'):
        plan(case)
    assert snapshot(case) == before


def test_plan_binds_current_head_even_after_unrelated_commit(case):
    register_case(case)
    first = plan(case)
    checkpoint(case)
    second = plan(case)
    assert second['input_head'] == store.read_head(case)['id']
    assert second['plan_hash'] != first['plan_hash']
    assert second['affected_attempt_ids'] == first['affected_attempt_ids']


def test_concurrent_head_change_is_rejected(case, monkeypatch):
    register_case(case)
    module = api()
    original = module._current
    def advance(root, head, session):
        original(root, head, session)
        checkpoint(root)
    monkeypatch.setattr(module, '_current', advance)
    with pytest.raises(ValueError, match='m1_head_conflict'):
        plan(case)


def test_issue_from_other_session_is_not_accepted_by_matching_local_id(case):
    register_case(case)
    head = store.read_head(case)
    head['state']['decisions'][0]['issue_threads'][0]['issue']['session_id'] = 'foreign-session'
    store.commit_record(case, expected_head=head['id'], command_id='foreign-issue-checkpoint', state=head['state'],
        event={**store._VERSION, 'type': 'synthetic_test_checkpoint', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_return_issue_invalid'):
        plan(case)


def test_public_return_fixture_and_cli_produce_same_read_only_plan(tmp_path, capsys):
    from researchclaw.codex.cli import main
    value = build_review_case(tmp_path, outcome='return_hypothesis')
    before = snapshot(tmp_path)
    assert main(['m1', 'return', 'plan', str(tmp_path), '--decision', value['decision_id'],
                 '--target', 'hypothesize', '--issues', 'synthetic-issue-H1', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == plan(tmp_path, decision_id=value['decision_id'], issue_ids=['synthetic-issue-H1'])
    assert result['reason_code'] == 'hypothesis_revision'
    assert snapshot(tmp_path) == before
