"""Atomic return execution against explicitly synthetic public review records."""
from copy import deepcopy
import importlib
import importlib.util
import json
import shutil

import pytest

from researchclaw.core.m1 import store, transitions
from researchclaw.core.m1.packets import prepare_node, register_outputs
from tests.codex_native.m1.helpers import build_review_case, checkpoint, encoded, submission


def budget_api():
    assert importlib.util.find_spec('researchclaw.core.m1.budgets'), 'M1 budget engine is missing'
    return importlib.import_module('researchclaw.core.m1.budgets')


def apply(root, plan, command='apply-return'):
    assert hasattr(transitions, 'apply_return'), 'M1 return application is missing'
    return transitions.apply_return(root, plan=plan, command_id=command)


@pytest.fixture(scope='module')
def return_base(tmp_path_factory):
    root = tmp_path_factory.mktemp('return-execution')
    build_review_case(root, outcome='return_hypothesis')
    return root


@pytest.fixture
def case(tmp_path, return_base):
    root = tmp_path / 'project'
    shutil.copytree(return_base, root)
    return root


def plan(root, target='hypothesize'):
    return transitions.plan_return(root, decision_id='synthetic-decision', target_node_id=target,
                                   issue_ids=['synthetic-issue-H1'])


def change_state(root, mutate):
    head = store.read_head(root)
    mutate(head['state'])
    store.commit_record(root, expected_head=head['id'], command_id='synthetic-state-' + head['id'],
        state=head['state'], event={**store._VERSION, 'type': 'synthetic_test_checkpoint',
        'payload': {'provenance_status': 'declared_only'}}, objects={})


@pytest.mark.parametrize(('used', 'limit', 'expected'), [(0, 2, True), (1, 2, True), (2, 2, False), (3, 2, False), (0, 0, False)])
def test_return_budget_is_a_ceiling(used, limit, expected):
    assert budget_api().can_start_return(used=used, limit=limit) is expected


@pytest.mark.parametrize(('used', 'limit'), [(-1, 2), (0, -1), (True, 2), (0, True), (0.0, 2), (0, '2')])
def test_budget_requires_nonnegative_exact_integers(used, limit):
    with pytest.raises(ValueError, match='m1_budget_invalid'):
        budget_api().can_start_return(used=used, limit=limit)


def test_apply_atomically_creates_one_prepared_revision_without_touching_history(case):
    before = store.read_head(case)
    result = apply(case, plan(case))
    after = store.read_head(case)
    assert len(after['events']) == len(before['events']) + 1
    assert after['events'][-1]['type'] == 'return_applied'
    assert after['state']['returns_used'] == 1
    assert after['state']['max_returns'] == 2
    assert after['state']['current_node_id'] == 'hypothesize'
    assert after['state']['attempts'][:-1] == before['state']['attempts']
    assert after['state']['artifacts'] == before['state']['artifacts']
    assert after['state']['approvals'] == before['state']['approvals']
    old = next(a for a in before['state']['attempts'] if a['node_id'] == 'hypothesize')
    new = result['attempt']
    assert new['revision'] == 2 and new['parent_attempt_id'] == old['id']
    assert new['id'] != old['id'] and new['status'] == 'prepared'
    assert result['packet']['attempt_id'] == new['id']
    assert result['transition']['to_attempt_id'] == new['id']
    assert after['state']['transitions'] == [result['transition']]
    prepared = prepare_node(case, 'hypothesize', command_id='prepare-returned')
    assert prepared['attempt'] == new and prepared['packet'] == result['packet']
    assert len(store.read_head(case)['state']['attempts']) == len(before['state']['attempts']) + 1
    for digest in before['objects']:
        assert store._read_file(store._store_path(case) / 'objects' / digest)


def test_exact_replay_after_later_head_returns_original_without_charge(case):
    value = plan(case)
    result = apply(case, value)
    checkpoint(case)
    head = store.read_head(case)
    assert apply(case, value) == result
    assert store.read_head(case) == head
    changed = {**value, 'schema_version': True}
    with pytest.raises(ValueError, match='m1_command_conflict'):
        apply(case, changed)
    assert store.read_head(case) == head


@pytest.mark.parametrize('field', ['rationale', 'affected_attempt_ids', 'approval_effects', 'plan_hash', 'id', 'schema_version', 'extra'])
def test_every_plan_field_is_verified_against_fresh_plan(case, field):
    value = plan(case)
    value[field] = True if field == 'schema_version' else 'tampered'
    head = store.read_head(case)
    with pytest.raises(ValueError, match='m1_return_plan_invalid'):
        apply(case, value)
    assert store.read_head(case) == head


def test_stale_plan_and_second_application_are_rejected(case):
    value = plan(case)
    checkpoint(case)
    with pytest.raises(ValueError, match='m1_head_conflict'):
        apply(case, value)
    current = plan(case)
    apply(case, current)
    head = store.read_head(case)
    with pytest.raises(ValueError, match='m1_head_conflict'):
        apply(case, current, 'second-apply')
    assert store.read_head(case) == head


def test_budget_exhaustion_does_not_create_attempt_or_charge(case):
    budget_api().set_return_budget(case, limit=0, note='Explicit synthetic user budget', command_id='budget-zero')
    value, head = plan(case), store.read_head(case)
    with pytest.raises(ValueError, match='m1_return_budget_exhausted'):
        apply(case, value)
    assert store.read_head(case) == head


@pytest.mark.parametrize(('limit', 'note'), [(-1, 'user'), (True, 'user'), (2.0, 'user'), (2, ''), (2, ' ')])
def test_explicit_budget_change_validates_limit_and_note(case, limit, note):
    head = store.read_head(case)
    with pytest.raises(ValueError, match='m1_budget_invalid'):
        budget_api().set_return_budget(case, limit=limit, note=note, command_id='budget-set')
    assert store.read_head(case) == head


def test_budget_change_records_user_declaration_and_replays(case):
    result = budget_api().set_return_budget(case, limit=3, note='Synthetic explicit user instruction', command_id='budget-set')
    assert result['budget']['max_returns'] == 3
    assert result['budget']['returns_used'] == 0
    assert result['change']['note'] == 'Synthetic explicit user instruction'
    assert result['change']['provenance_status'] == 'declared_only'
    checkpoint(case)
    head = store.read_head(case)
    assert budget_api().set_return_budget(case, limit=3, note='Synthetic explicit user instruction', command_id='budget-set') == result
    with pytest.raises(ValueError, match='m1_command_conflict'):
        budget_api().set_return_budget(case, limit=4, note='Synthetic explicit user instruction', command_id='budget-set')
    assert store.read_head(case) == head


def repeat_review(root, *, work=None, different_issue_evidence=False):
    """Publicly register unchanged bytes and a fresh synthetic council/decision."""
    from researchclaw.core.m1 import council, decisions
    before = store.read_head(root)
    old_session = next(iter(before['state']['sessions'].values()))
    packet = before['state']['packets'][before['state']['attempts'][-1]['packet_id']]
    latest = {ref['logical_path']: ref for ref in before['state']['artifacts']}
    files = {path: store._read_file(store._store_path(root) / 'objects' / latest[path]['sha256'])
             for path in packet['allowed_outputs']}
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files),
                              command_id='unchanged-registration')
    assert result['status'] == 'review_pending', result
    original_requests = [event['payload'].get('request', {}) for event in before['events']]
    original_prepare = next(r for r in original_requests if r.get('operation') == 'prepare_council')
    session = council.prepare_council(root, attempt_id=packet['attempt_id'],
        assignments=original_prepare['assignments'], command_id='repeat-council')['session']
    current_refs = {ref['logical_path']: ref for ref in session['input_refs']}
    replacements = {old_session['id']: session['id'], old_session['input_binding']: session['input_binding'],
                    'synthetic-issue-H1': 'fresh-issue-H1', 'synthetic-decision': 'fresh-decision'}
    replacements.update({ref['id']: current_refs[ref['logical_path']]['id'] for ref in old_session['input_refs']})
    def rebind(value):
        if type(value) is str:
            return replacements.get(value, value)
        if type(value) is list:
            return [rebind(item) for item in value]
        if type(value) is dict:
            return {key: rebind(item) for key, item in value.items()}
        return value
    operations = {'register_initial': council.register_initial, 'register_response': council.register_response,
                  'register_final_position': council.register_final_position, 'register_decision': decisions.register_decision}
    for index, request in enumerate(original_requests):
        if request.get('operation') not in operations:
            continue
        args = rebind({key: value for key, value in request.items() if key != 'operation'})
        if request['operation'] == 'register_initial' and different_issue_evidence:
            for issue in args['payload']['open_issues']:
                issue['evidence_refs'] = [next(r['id'] for r in session['input_refs']
                                              if r['id'] not in issue['evidence_refs'])]
        if request['operation'] == 'register_decision':
            frozen = store.read_head(root)['state']['sessions'][session['id']]['disclosed_final_positions']
            args['payload']['positions'] = deepcopy(frozen)
            args['payload']['dissent'] = deepcopy(frozen)
            if work is not None:
                args['payload']['proposed_work'] = work
        operations[request['operation']](root, **args, command_id='repeat-' + str(index))
    return transitions.plan_return(root, decision_id='fresh-decision', target_node_id='hypothesize',
                                   issue_ids=['fresh-issue-H1'])


@pytest.mark.parametrize('reordered_work', [False, True])
def test_same_content_fresh_artifact_issue_session_decision_ids_are_not_new_basis(case, reordered_work):
    work = ['Revise the mechanism claim against the observation.', 'Compare the control group.']
    if reordered_work:
        change_state(case, lambda state: state['decisions'][0].update(proposed_work=work))
    apply(case, plan(case))
    repeated = repeat_review(case, work=list(reversed(work)) if reordered_work else None)
    # Even explicitly changing the ceiling must not count as new research input.
    budget_api().set_return_budget(case, limit=3, note='Synthetic explicit budget instruction', command_id='budget-bump')
    # A cached digest from a prior projection must not defeat immutable-basis comparison.
    change_state(case, lambda state: state['transitions'][0].update(basis_hash='0' * 64))
    repeated = transitions.plan_return(case, decision_id='fresh-decision', target_node_id='hypothesize',
                                      issue_ids=['fresh-issue-H1'])
    head = store.read_head(case)
    with pytest.raises(ValueError, match='m1_no_new_basis'):
        apply(case, repeated, 'duplicate-basis')
    assert store.read_head(case) == head


def test_additional_declared_work_supplies_new_return_basis(case):
    apply(case, plan(case))
    repeated = repeat_review(case, work=['Compare the specific measurement confounder with the registered source.'])
    result = apply(case, repeated, 'new-work')
    assert result['budget']['returns_used'] == 2
    assert result['attempt']['revision'] == 3
    assert result['budget']['exhausted'] is True


def test_explicit_new_search_work_can_start_before_new_files_exist(case):
    def retarget(state):
        state['decisions'][0].update(return_target='search', proposed_work=['Search a new database for comparable control groups.'])
    change_state(case, retarget)
    before = store.read_head(case)
    result = apply(case, plan(case, 'search'))
    assert result['attempt']['node_id'] == 'search'
    assert store.read_head(case)['state']['artifacts'] == before['state']['artifacts']


def test_cli_apply_and_budget_set_use_public_contract(case, tmp_path, capsys):
    from researchclaw.codex.cli import main
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan(case)))
    assert main(['m1', 'return', 'apply', str(case), '--plan', str(path), '--command-id', 'cli-return', '--json']) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['attempt']['revision'] == 2
    assert main(['m1', 'budget', 'set', str(case), '--max-returns', '1', '--note', 'User sets ceiling', '--command-id', 'cli-budget', '--json']) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['budget']['returns_used'] == 1
    assert value['budget']['exhausted'] is True


def test_issue_bound_to_different_evidence_is_a_new_basis(case):
    apply(case, plan(case))
    repeated = repeat_review(case, different_issue_evidence=True)
    result = apply(case, repeated, 'new-issue-evidence')
    assert result['budget']['returns_used'] == 2
