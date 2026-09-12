"""Pure preparation and result-registration policy for verification work.

Registration freezes declared work and records supplied results. It performs no
experiment or resource allocation, creates no assignment, and never changes issue
status. Budget registration only preserves declared scope and resource limits.
"""
from copy import deepcopy

from . import store
from .contracts import validate_record
from .issues import _Inputs, _require


def _unique_record(state, record, collection, exists_reason):
    _require(record['id'] not in state.get(collection, {}), exists_reason)
    all_records = [*state.get('verifications', {}).values(),
                   *state.get('verification_results', {}).values()]
    _require(all(item.get('event_id') != record['event_id'] for item in all_records),
             'verification_event_exists')


def prepare_verification(snapshot: dict, payload: dict) -> dict:
    """Return a transition plan that freezes a verification before results."""
    _require(type(payload) is dict and set(payload) == {'verification'},
             'verification_payload_invalid')
    supplied = payload['verification']
    _require(type(supplied) is dict and isinstance(supplied.get('acceptance_rule'), str)
             and bool(supplied['acceptance_rule'].strip()), 'acceptance_rule_missing')
    verification = deepcopy(supplied)
    _require(not validate_record('Verification', verification), 'verification_record_invalid')
    inputs = _Inputs(snapshot)
    state = inputs.state
    _require(verification['project_id'] == inputs.project, 'verification_project_mismatch')
    _unique_record(state, verification, 'verifications', 'verification_exists')
    _require(bool(verification['issue_ids'])
             and len(set(verification['issue_ids'])) == len(verification['issue_ids']),
             'verification_issue_invalid')
    owner = inputs.assignment(verification['owner_assignment_id'])
    _require(owner['role'] == 'owner' and verification['producer_id'] == owner['actor_id'],
             'verification_owner_mismatch')
    for issue_id in verification['issue_ids']:
        issue = inputs.registered('issues', issue_id, 'Issue')
        _require(issue['resolution_condition'] == verification['acceptance_rule'],
                 'verification_binding_mismatch')
    for ref in [verification['budget_ref'], *verification['input_refs'],
                *verification['observation_refs']]:
        inputs.reference(ref)
    collection = {**state.get('verifications', {}), verification['id']: verification}
    return {'state_patch': {'verifications': collection},
            'event': {**store._VERSION, 'type': 'verification_prepared', 'payload': verification},
            'object_inputs': {f"verifications/{verification['id']}": store._canonical(verification)}}


def register_verification_result(snapshot: dict, payload: dict) -> dict:
    """Return a transition plan bound to one exact prepared revision."""
    _require(type(payload) is dict and set(payload) == {'verification_ref', 'result'},
             'verification_payload_invalid')
    result = deepcopy(payload['result'])
    _require(type(result) is dict and not validate_record('VerificationResult', result),
             'verification_record_invalid')
    inputs = _Inputs(snapshot)
    state = inputs.state
    _require(result['project_id'] == inputs.project, 'verification_project_mismatch')
    _unique_record(state, result, 'verification_results', 'verification_result_exists')
    verification = inputs.reference(payload['verification_ref'], 'verifications', 'Verification')
    _require(result['verification_id'] == verification['id'], 'verification_binding_mismatch')
    for issue_id in verification['issue_ids']:
        inputs.verification(verification['id'], issue_id)
    owner = inputs.assignment(verification['owner_assignment_id'])
    _require(owner['role'] == 'owner'
             and verification['producer_id'] == owner['actor_id']
             and result['producer_id'] == owner['actor_id'], 'verification_owner_mismatch')
    output_data = [inputs.reference(ref) for ref in result['output_refs']]
    for ref in result['observation_refs']:
        inputs.reference(ref)
    if result['outcome'] in ('supported', 'refuted'):
        _require(bool(output_data) and all(output_data), 'verification_output_missing')
        _require(verification['acceptance_rule'] in result['checked_scope'],
                 'verification_scope_missing')
    else:
        _require(bool(result['limitations']), 'verification_limitation_missing')
    collection = {**state.get('verification_results', {}), result['id']: result}
    return {'state_patch': {'verification_results': collection},
            'event': {**store._VERSION, 'type': 'verification_result_registered', 'payload': result},
            'object_inputs': {f"verification-results/{result['id']}": store._canonical(result)}}


def register_verification_budget(snapshot: dict, payload: dict) -> dict:
    """Record declared resources and scope; no allocation, enforcement or consent."""
    _require(type(payload) is dict and set(payload) == {'budget'}, 'verification_budget_invalid')
    budget = deepcopy(payload['budget'])
    _require(type(budget) is dict and not validate_record('VerificationBudget', budget),
             'verification_budget_invalid')
    inputs = _Inputs(snapshot)
    _require(budget['project_id'] == inputs.project, 'verification_project_mismatch')
    owner = inputs.assignment(budget['owner_assignment_id'])
    _require(owner['role'] == 'owner' and owner['actor_id'] == budget['producer_id'],
             'verification_owner_mismatch')
    _require(bool(budget['resource_limits']) and bool(budget['input_refs']), 'verification_budget_invalid')
    records = inputs.state.get('verification_budgets', {})
    _require(budget['id'] not in records and all(budget['event_id'] != r['event_id'] for r in records.values()),
             'verification_budget_exists')
    for ref in [*budget['input_refs'], *budget['observation_refs']]:
        inputs.reference(ref)
    return {'state_patch': {'verification_budgets': {**records, budget['id']: budget}},
            'event': {**store._VERSION, 'type': 'verification_budget_registered', 'payload': budget},
            'object_inputs': {'verification-budgets/' + budget['id']: store._canonical(budget)}}
