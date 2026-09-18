"""Pure literal-repeat, correction, budget and resume policy.

Consumes backed prerequisites; does not execute, create approvals or count work.
See budget-inputs.md for the closed descriptor and structural limits.
"""
import math
import unicodedata
from uuid import UUID

from . import store
from .dependencies import _References, _node
from .gates import _approval
from .issues import _Inputs, _require
from .return_policy import return_mode, require_return_plan

_ENVELOPE = {'schema_version', 'workflow_version', 'id', 'project_id', 'event_id',
             'producer_id', 'content_origin', 'provenance_status', 'observation_refs'}
_WORK = _ENVELOPE | {'assignment_id', 'milestone', 'node', 'question', 'input_refs', 'work', 'acceptance_rule'}
_PAYLOAD = {'work', 'resource_request', 'correction_ref', 'correction_approval_ref', 'semantic_status', 'resume_ref'}
_COLLECTIONS = {'work_ledgers', 'work_records', 'work_corrections', 'assignments', 'approval_bindings', 'approval_receipts'}
_STATUSES = {'pending', 'completed', 'failed', 'inconclusive', 'awaiting_input', 'blocked_budget'}
_BUDGET_REASONS = {'returns_exhausted', 'verification_runs_exhausted', 'execution_cost_exhausted'}


def _uuid(value):
    try:
        return type(value) is str and str(UUID(value)) == value
    except ValueError:
        return False


def _text(value):
    return type(value) is str and bool(value.strip())


def _normal(value):
    return ' '.join(unicodedata.normalize('NFC', value).split())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _count(value):
    return type(value) is int and value >= 0


def _output(reasons, work=None, previous=None):
    codes = list(dict.fromkeys(reasons))
    status = 'blocked_budget' if set(codes) & _BUDGET_REASONS else ('awaiting_input' if codes else 'ready')
    actions = [f'Provide a valid correction for {code} before reassessing work.' for code in codes]
    next_actions = [{'kind': status, 'reason_code': code} for code in codes]
    if not codes:
        next_actions = [{'kind': 'assess_authorized_work', 'milestone': work['milestone'], 'node': work['node']}]
    return dict(ready=not codes, reason_codes=codes, required_actions=actions, status=status,
                next_actions=next_actions, previous_status=previous)


def _resources(value):
    _require(type(value) is dict and set(value) == {'returns', 'verification_runs', 'estimated_cost', 'cost_status'}
             and _count(value['returns']) and _count(value['verification_runs'])
             and ((value['cost_status'] == 'known' and _number(value['estimated_cost']))
                  or (value['cost_status'] == 'unknown' and value['estimated_cost'] is None)), 'resource_request_invalid')


def _signature(inputs, refs, work, *, current):
    _require(type(work) is dict and set(work) == _WORK
             and all(type(work[key]) is type(value) and work[key] == value
                     for key, value in store._VERSION.items())
             and all(_uuid(work[key]) for key in ('id', 'project_id', 'event_id', 'assignment_id'))
             and work['project_id'] == inputs.project and _text(work['producer_id'])
             and work['milestone'] in ('M1', 'M2', 'M3')
             and work['content_origin'] in ('real', 'synthetic', 'mixed')
             and work['provenance_status'] in ('declared_only', 'host_observed')
             and all(_text(work[key]) for key in ('node', 'question', 'work', 'acceptance_rule'))
             and type(work['input_refs']) is list and bool(work['input_refs'])
             and type(work['observation_refs']) is list
             and (work['provenance_status'] != 'host_observed' or bool(work['observation_refs'])), 'work_invalid')
    if current:
        actor = inputs.assignment(work['assignment_id'])
        _require(actor['role'] == 'owner' and actor['milestone'] == work['milestone']
                 and actor['actor_id'] == work['producer_id'], 'work_assignment_invalid')
    for ref in [*work['input_refs'], *work['observation_refs']]:
        is_current = refs.resolve(ref)
        _require(not current or is_current, 'work_input_stale')
    nodes = [_node(ref) for ref in work['input_refs']]
    _require(len(nodes) == len(set(nodes)), 'work_invalid')
    descriptor = {key: _normal(work[key]) for key in ('milestone', 'node', 'question', 'work', 'acceptance_rule')}
    descriptor['input_refs'] = [list(node) for node in sorted(nodes)]
    return store._hash(store._canonical(descriptor))


def _ledger(inputs, refs):
    ledger = inputs.registered('work_ledgers', inputs.state.get('work_ledger_id'))
    _require(set(ledger) == {'id', 'project_id', 'work_refs'} and _uuid(ledger['id'])
             and type(ledger['work_refs']) is list, 'work_ledger_invalid')
    history = {}
    for _, ancestor in inputs.history:
        for identity, record in ancestor['state'].get('work_records', {}).items():
            _require(identity not in history or history[identity] == record, 'work_ledger_invalid')
            history[identity] = record
    _require(inputs.state.get('work_records', {}) == history, 'work_ledger_invalid')
    registered = {}
    for ref in ledger['work_refs']:
        record = inputs.reference(ref, 'work_records')
        _require(set(record) == {'id', 'project_id', 'work', 'resource_request', 'status', 'correction_ref'}
                 and _uuid(record['id']) and record['status'] in _STATUSES
                 and record['id'] not in registered, 'work_ledger_invalid')
        signature = _signature(inputs, refs, record['work'], current=False)
        _resources(record['resource_request'])
        registered[record['id']] = (record, ref, signature)
    _require(set(registered) == set(history), 'work_ledger_invalid')
    for record, _, signature in registered.values():
        if record['correction_ref'] is not None:
            correction, previous, _ = _correction(inputs, refs, record['correction_ref'])
            _require(previous['id'] in registered and previous['id'] != record['id']
                     and correction['replacement_signature'] == signature, 'work_ledger_invalid')
    return registered


def _correction(inputs, refs, ref):
    record = inputs.reference(ref, 'work_corrections')
    _require(set(record) == {'id', 'project_id', 'previous_work_ref', 'replacement_signature', 'rationale', 'evidence_refs'}
             and _uuid(record['id']) and store._is_digest(record['replacement_signature'])
             and _text(record['rationale']) and type(record['evidence_refs']) is list and bool(record['evidence_refs']), 'correction_invalid')
    prior = inputs.reference(record['previous_work_ref'], 'work_records')
    for evidence in record['evidence_refs']:
        refs.resolve(evidence)
    evidence_nodes = [_node(ref) for ref in record['evidence_refs']]
    _require(len(evidence_nodes) == len(set(evidence_nodes)), 'correction_invalid')
    content = dict(previous_work=list(_node(record['previous_work_ref'])), replacement_signature=record['replacement_signature'],
                   rationale=_normal(record['rationale']), evidence=sorted(list(_node(r)) for r in record['evidence_refs']))
    return record, prior, store._hash(store._canonical(content))


def _budget_reasons(state, request):
    mode = return_mode(state)
    _require(all(_count(state.get(key)) for key in ('max_returns', 'returns_used', 'max_verification_runs', 'verification_runs_used')),
             'budget_invalid')
    limit, observed = state.get('execution_cost_limit'), state.get('observed_cost')
    _require((limit is None or _number(limit)) and
             ((state.get('cost_status') == 'unknown' and observed is None)
              or (state.get('cost_status') == 'known' and _number(observed))), 'budget_invalid')
    reasons = []
    for used, maximum, increment, reason in [('returns_used', 'max_returns', 'returns', 'returns_exhausted'),
        ('verification_runs_used', 'max_verification_runs', 'verification_runs', 'verification_runs_exhausted')]:
        if increment == 'returns' and mode == 'evidence_driven':
            continue
        if request[increment] and state[used] + request[increment] > state[maximum]:
            reasons.append(reason)
    if limit is not None:
        if state['cost_status'] == 'unknown' or request['cost_status'] == 'unknown':
            reasons.append('cost_unknown')
        elif observed + request['estimated_cost'] > limit:
            reasons.append('execution_cost_exhausted')
    return reasons


def assess_next_work(snapshot: dict, payload: dict) -> dict:
    """Assess concrete successor work without changing its recorded predecessor."""
    try:
        inputs = _Inputs(snapshot)
    except (KeyError, TypeError, ValueError):
        return _output(['work_context_missing'])
    if any(type(record['state'].get(name, {})) is not dict
           for _, record in inputs.history for name in _COLLECTIONS):
        return _output(['work_collection_invalid'])
    if type(payload) is not dict or set(payload) not in (_PAYLOAD, _PAYLOAD | {'return_plan'}):
        return _output(['work_payload_invalid'])
    try:
        refs = _References(inputs)
        signature = _signature(inputs, refs, payload['work'], current=True)
    except (KeyError, TypeError, ValueError):
        return _output(['work_invalid'])
    try:
        _resources(payload['resource_request'])
    except (KeyError, TypeError, ValueError):
        return _output(['resource_request_invalid'])
    try:
        records = _ledger(inputs, refs)
    except (KeyError, TypeError, ValueError):
        return _output(['work_ledger_invalid'])
    previous, reasons = None, []
    try:
        mode = return_mode(inputs.state)
    except ValueError:
        return _output(['return_policy_invalid'])
    if 'return_plan' in payload or (mode == 'evidence_driven' and payload['resource_request']['returns']):
        try:
            require_return_plan(inputs, refs, payload.get('return_plan'), records)
        except (KeyError, TypeError, ValueError, StopIteration):
            reasons.append('return_plan_required')
    if payload['resume_ref'] is not None:
        try:
            prior = inputs.reference(payload['resume_ref'], 'work_records')
            _require(prior['id'] in records, 'resume_invalid')
            previous = prior['status']
        except (KeyError, TypeError, ValueError):
            return _output(['resume_invalid'])
    if payload['semantic_status'] not in ('literal_only', 'uncertain'):
        reasons.append('work_payload_invalid')
    elif payload['semantic_status'] == 'uncertain':
        reasons.append('semantic_identity_uncertain')
    repeated = {identity for identity, (_, _, old_signature) in records.items() if old_signature == signature}
    correction_valid = False
    correction_ref, approval_ref = payload['correction_ref'], payload['correction_approval_ref']
    if correction_ref is not None or approval_ref is not None:
        try:
            correction, old, content = _correction(inputs, refs, correction_ref)
            _require(old['id'] in records and correction['replacement_signature'] == signature,
                     'correction_invalid')
            _require(not repeated or old['id'] in repeated, 'correction_invalid')
            used = False
            for record, _, _ in records.values():
                if record['correction_ref'] is not None:
                    _, _, prior_content = _correction(inputs, refs, record['correction_ref'])
                    used |= content == prior_content
            _require(not used, 'correction_already_used')
            _approval(inputs, approval_ref, correction_ref)
            approval = inputs.reference(approval_ref, 'approval_bindings', 'ApprovalBinding')
            _require(correction['previous_work_ref'] in approval['scope_refs'], 'correction_invalid')
            _require(all(refs.resolve(ref) for ref in correction['evidence_refs']), 'correction_invalid')
            correction_valid = True
        except (KeyError, TypeError, ValueError, StopIteration) as error:
            reasons.append('correction_already_used' if str(error) == 'correction_already_used' else 'correction_invalid')
    if repeated and not correction_valid:
        reasons.append('repeated_work')
    try:
        reasons.extend(_budget_reasons(inputs.state, payload['resource_request']))
    except (KeyError, TypeError, ValueError):
        reasons.append('budget_invalid')
    return _output(reasons, payload['work'], previous)
