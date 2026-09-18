"""Evidence-driven return policy keeps history and resource boundaries."""
from copy import deepcopy

import pytest

from researchclaw.core.research_graph import commands, store, work_accounting
from tests.codex_native.research_graph.test_budgets import Fixture, uid


POLICY = dict(mode='evidence_driven', rationale='Judge the missing evidence and next action, not the count.',
              authorization_basis='Synthetic user instruction: use evidence-driven returns.')


def enable(f, command_id=None):
    f.head = commands.apply_command(f.root, operation='work.return_policy.set', payload=POLICY,
                                   expected_head=f.head['id'], command_id=command_id or uid())


def returning(f):
    _, previous = f.prior('inconclusive')
    f.work['work'] = 'Find the measurement protocol and reassess the comparison'
    f.resources['returns'] = 1
    f.payload['return_plan'] = dict(previous_work_ref=previous, trigger='missing_evidence',
        gap='Temperature was not reported.', affected_refs=[f.source],
        decision_impact='Decides whether the two measurements can be compared.',
        evidence_needed='Temperature and conditioning protocol from the source.',
        if_unavailable='Hold the temperature-sensitive comparison; continue the other analyses.')


def test_policy_change_preserves_counts_history_and_is_idempotent(tmp_path):
    f = Fixture(tmp_path); f.patch(returns_used=7)
    before = store.read_head(tmp_path); enable(f, 'policy-once')
    changed = {key for key in f.head['state'] if f.head['state'].get(key) != before['state'].get(key)}
    assert changed == {'return_policy'}
    assert f.head['state']['returns_used'] == 7 and f.head['state']['max_returns'] == 3
    first = f.head
    retry = commands.apply_command(tmp_path, operation='work.return_policy.set', payload=POLICY,
                                   expected_head=before['id'], command_id='policy-once')
    assert retry == first and store.read_head(tmp_path) == first


def test_supported_return_can_continue_beyond_old_count_with_no_state_write(tmp_path):
    f = Fixture(tmp_path); returning(f); f.patch(returns_used=700); enable(f)
    before = store.read_head(tmp_path)
    assert f.assess()['ready'] is True
    assert store.read_head(tmp_path) == before


@pytest.mark.parametrize('fault', ['absent', 'empty_gap', 'foreign_ref', 'missing_work', 'duplicate_refs'])
def test_return_requires_concrete_plan_and_resolvable_context(tmp_path, fault):
    f = Fixture(tmp_path); returning(f); enable(f)
    plan = f.payload['return_plan']
    if fault == 'absent': del f.payload['return_plan']
    if fault == 'empty_gap': plan['gap'] = ' '
    if fault == 'foreign_ref': plan['affected_refs'][0] = {**f.source, 'project_id': uid()}
    if fault == 'missing_work': plan['previous_work_ref'] = f.source
    if fault == 'duplicate_refs': plan['affected_refs'].append(f.source)
    result = f.assess()
    assert not result['ready'] and 'return_plan_required' in result['reason_codes']


def test_plan_does_not_authorize_identical_work_or_semantic_uncertainty(tmp_path):
    f = Fixture(tmp_path); returning(f); enable(f)
    f.work['work'] = 'Compare RNA effect'
    assert 'repeated_work' in f.assess()['reason_codes']
    f.work['work'] = 'A differently worded repetition'
    f.payload['semantic_status'] = 'uncertain'
    assert 'semantic_identity_uncertain' in f.assess()['reason_codes']


@pytest.mark.parametrize('state,reason', [
    ({'verification_runs_used': 10}, 'verification_runs_exhausted'),
    ({'execution_cost_limit': 1, 'observed_cost': 0, 'cost_status': 'known'}, 'execution_cost_exhausted'),
    ({'execution_cost_limit': 1}, 'cost_unknown'),
])
def test_evidence_policy_does_not_bypass_other_resources(tmp_path, state, reason):
    f = Fixture(tmp_path); returning(f); f.patch(**state); enable(f)
    assert f.assess()['reason_codes'] == [reason]


def test_missing_or_invalid_policy_does_not_silently_disable_limit(tmp_path):
    f = Fixture(tmp_path); f.resources['returns'] = 1; f.patch(returns_used=7)
    assert 'returns_exhausted' in f.assess()['reason_codes']
    f.patch(return_policy={'mode': 'unlimited'})
    assert 'return_policy_invalid' in f.assess()['reason_codes']


@pytest.mark.parametrize('change', [{'authorization_basis': ' '}, {'mode': 'unlimited'}, {'max_returns': 999}])
def test_invalid_policy_command_leaves_head_unchanged(tmp_path, change):
    f = Fixture(tmp_path); before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='return_policy_invalid'):
        commands.apply_command(tmp_path, operation='work.return_policy.set', payload={**POLICY, **change},
                               expected_head=f.head['id'], command_id=uid())
    assert store.read_head(tmp_path) == before


def test_accounting_still_records_returns_but_no_longer_blocks_handoff(tmp_path):
    from tests.codex_native.research_graph.test_m1_scope import Fixture as NativeFixture
    f = NativeFixture(tmp_path)
    f.register()
    for number in range(4):
        f.register(f.node(previous_ref=f.node_ref(), revision_reason='Clarify scope',
                          content=dict(user_goal=f'Scope refinement {number}', user_constraints=[], agent_assumptions=[])))
    f.apply('council.prepare', f.council_payload())
    f.submitted = {phase: [] for phase in ('initial', 'response', 'final')}
    f.complete()
    for source in work_accounting.work_sources(f.snapshot()):
        f.apply('m1.work.record', dict(record_id=uid(), source_kind=source['source_kind'], source_ref=source['source_ref']))
    f.apply('work_ledger.refresh', dict(ledger_id=uid()))
    assert work_accounting.accounting_status(f.snapshot())['reason_codes'] == ['returns_exhausted']
    before = deepcopy(f.head['state'])
    enable(f)
    result = work_accounting.accounting_status(f.snapshot())
    assert result['ready'] is True
    assert result['return_policy'] == dict(mode='evidence_driven', returns_used=4, count_limit=None)
    assert f.head['state']['work_records'] == before['work_records']
    assert f.head['state']['returns_used'] == 4


def test_cli_assesses_saved_successor_without_starting_work(tmp_path, capsys):
    import json
    from researchclaw.codex.cli import main
    f = Fixture(tmp_path / 'project'); returning(f); enable(f)
    payload = tmp_path / 'successor.json'
    payload.write_text(json.dumps(f.payload))
    before = store.read_head(f.root)
    assert main(['research', 'assess-work', str(f.root), '--payload', str(payload), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['ready'] is True
    assert store.read_head(f.root) == before
