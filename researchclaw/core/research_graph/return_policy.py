"""Explicit return policy and concrete successor context; no research execution."""
from copy import deepcopy

from . import store
from .dependencies import _node
from .issues import _require

_FIELDS = {'mode', 'rationale', 'authorization_basis'}
_PLAN = {'previous_work_ref', 'trigger', 'gap', 'affected_refs', 'decision_impact',
         'evidence_needed', 'if_unavailable'}


def _text(value):
    return type(value) is str and bool(value.strip())


def return_mode(state):
    # Existing snapshots keep their original policy until explicitly changed.
    if 'return_policy' not in state:
        return 'count_limited'
    policy = state['return_policy']
    _require(type(policy) is dict and set(policy) == _FIELDS
             and policy['mode'] == 'evidence_driven'
             and all(_text(policy[key]) for key in ('rationale', 'authorization_basis')),
             'return_policy_invalid')
    return policy['mode']


def set_return_policy(snapshot, payload):
    return_mode({'return_policy': payload})
    policy = deepcopy(payload)
    # This basis is a declaration, not a scientific or execution approval.
    return dict(state_patch={'return_policy': policy},
                event={**store._VERSION, 'type': 'work_return_policy_set', 'payload': policy},
                object_inputs={})


def require_return_plan(inputs, refs, plan, records):
    """Validate traceability, not the scientific adequacy of a written plan."""
    _require(type(plan) is dict and set(plan) == _PLAN
             and plan['trigger'] in ('missing_evidence', 'hypothesis_problem', 'repeated_discussion')
             and all(_text(plan[key]) for key in ('gap', 'decision_impact', 'evidence_needed', 'if_unavailable'))
             and type(plan['affected_refs']) is list and bool(plan['affected_refs']), 'return_plan_required')
    prior = inputs.reference(plan['previous_work_ref'], 'work_records')
    _require(prior['id'] in records, 'return_plan_required')
    for ref in plan['affected_refs']:
        _require(refs.resolve(ref), 'return_plan_required')
    nodes = [_node(ref) for ref in plan['affected_refs']]
    _require(len(nodes) == len(set(nodes)), 'return_plan_required')
