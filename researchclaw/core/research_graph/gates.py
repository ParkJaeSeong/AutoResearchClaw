"""Pure, fail-closed milestone policy assessment; see gate-inputs.md.

Consumes existing responsibility and approval records. Never creates authority,
executes work, or certifies scientific truth.
"""
from uuid import UUID

from . import store
from .contracts import validate_record
from .issues import _Inputs, _TRANSITIONS, _require
from .positions import validate_rationale_links

_FIELDS = {'id', 'project_id', 'milestone', 'kind', 'target_id', 'input_binding',
           'author_assignment_ids', 'required_roles', 'submission_refs', 'source_refs',
           'approval_refs', 'decision_ref'}
_COLLECTIONS = {'gate_requirements', 'assignments', 'approval_bindings', 'approval_receipts',
                'positions', 'decisions', 'issues', 'review_sessions',
                'position_acknowledgements', 'verifications', 'verification_results',
                'transfer_acceptances', 'imported_issue_states'}
_ROLES = {'M1': {'domain', 'methodology', 'critical'},
          'M2': {'domain', 'methodology', 'reproducibility'},
          'M3': {'domain', 'methodology', 'audit'}}


def _result(reasons, unresolved=()):
    codes = list(dict.fromkeys(reasons))
    return {'ready': not codes, 'reason_codes': codes,
            'required_actions': [f'Correct {code} before reassessing this gate.' for code in codes],
            'unresolved_issue_ids': sorted(set(unresolved))}


def _nonempty_list(value):
    return type(value) is list and bool(value)


def _status(inputs, issue):
    events = [{key: value for key, value in event['payload'].items() if key != '_command_request'}
              for event in inputs.history[-1][1]['events'] if event['type'] == 'issue_event']
    imported = issue['id'] in inputs.state.get('imported_issue_states', {})
    prior = [event for event in events if event.get('issue_id') == issue['id']]
    current = 'open' if imported and (not prior or prior[0].get('from_status') is not None) else None
    latest = None
    identities = set()
    for event in events:
        _require(type(event) is dict, 'issue_history_invalid')
        if event.get('issue_id') != issue['id']:
            continue
        data = store._canonical(event)
        digest = store._hash(data)
        _require(not validate_record('IssueEvent', event)
                 and event['project_id'] == inputs.project
                 and inputs.objects.get(digest) == data
                 and digest in inputs.history[-1][1]['objects']
                 and event['id'] not in identities
                 and event['from_status'] == current
                 and event['to_status'] in _TRANSITIONS.get(current, set()), 'issue_history_invalid')
        identities.add(event['id'])
        current, latest = event['to_status'], event
    _require(current is not None, 'issue_history_invalid')
    return current, latest


def _accepted_transfer(inputs, issue, event):
    owner = inputs.assignment(event['owner_assignment_id'])
    _require(owner['role'] == 'owner' and owner['milestone'] == 'M2'
             and event['to_milestone'] == 'M2', 'transfer_acceptance_invalid')
    verification = inputs.verification(event['verification_id'], issue['id'])
    _require(verification['owner_assignment_id'] == owner['id'], 'transfer_acceptance_invalid')
    acceptance = inputs.registered('transfer_acceptances', event['acceptance_event_id'])
    expected = dict(id=event['acceptance_event_id'], project_id=inputs.project,
                    issue_id=issue['id'], owner_assignment_id=owner['id'],
                    verification_id=verification['id'], to_milestone='M2',
                    accepted=True, producer_id=owner['actor_id'])
    _require(acceptance == expected and acceptance['accepted'] is True, 'transfer_acceptance_invalid')
    first = next(h['state'] for _, h in inputs.history
                 if h['state'].get('transfer_acceptances', {}).get(acceptance['id']) == acceptance)
    _require(first.get('verifications', {}).get(verification['id']) == verification
             and first.get('assignments', {}).get(owner['id']) == owner, 'transfer_acceptance_stale')


def _approval(inputs, ref, binding):
    approval = inputs.reference(ref, 'approval_bindings', 'ApprovalBinding')
    _require(approval['validity'] == 'valid', 'approval_not_current')
    _require(approval['binding'] == binding and binding in approval['scope_refs'], 'approval_invalid')
    for source in [approval['binding'], *approval['scope_refs'], *approval['observation_refs']]:
        inputs.reference(source)
    receipt = inputs.reference(approval['existing_receipt_ref'], 'approval_receipts')
    _require(set(receipt) == {'id', 'project_id', 'producer_id', 'decision', 'binding', 'scope_refs'}
             and receipt['decision'] == 'approved'
             and type(receipt['producer_id']) is str and bool(receipt['producer_id'].strip())
             and receipt['binding'] == approval['binding']
             and receipt['scope_refs'] == approval['scope_refs'], 'approval_invalid')
    receipt_index = next(i for i, (head, _) in enumerate(inputs.history)
                         if head == approval['existing_receipt_ref']['head_id'])
    approval_index = next(i for i, (_, h) in enumerate(inputs.history)
                          if approval['id'] in h['state'].get('approval_bindings', {}))
    _require(receipt_index < approval_index, 'approval_invalid')


def assess_gate(snapshot: dict, *, milestone: str, gate_id: str) -> dict:
    """Assess one backed gate declaration from commands.read_policy_snapshot."""
    try:
        inputs = _Inputs(snapshot)
    except (KeyError, TypeError, ValueError):
        return _result(['gate_context_missing'])
    # Typed reference helpers require mappings at both named ancestors and HEAD.
    # Reject declared malformed collections explicitly, without swallowing errors
    # from unrelated policy code. Absent collections retain prerequisite errors.
    if any(type(record['state'].get(name, {})) is not dict
           for _, record in inputs.history for name in _COLLECTIONS):
        return _result(['gate_collection_invalid'])
    try:
        _require(type(gate_id) is str and str(UUID(gate_id)) == gate_id, 'gate_invalid')
        gate = inputs.registered('gate_requirements', gate_id)
        if gate.get('profile') == 'native_m1_handoff':
            from .handoffs import assess_native_handoff
            _require(milestone == 'M1', 'gate_invalid')
            return assess_native_handoff(snapshot, gate)
        _require(set(gate) == _FIELDS and milestone in _ROLES
                 and gate['milestone'] == milestone and gate['kind'] in ('node', 'handoff', 'finalization')
                 and type(gate['target_id']) is str and bool(gate['target_id'].strip()), 'gate_invalid')
        if gate['kind'] == 'handoff':
            _require(gate['target_id'] == {'M1': 'M2', 'M2': 'M3'}.get(milestone), 'gate_invalid')
        inputs.reference(gate['input_binding'])
    except (KeyError, TypeError, ValueError):
        return _result(['gate_prerequisite_missing'])

    reasons, unresolved = [], []
    authors, reviewer_actors, reviewer_ids = set(), set(), set()
    try:
        ids = gate['author_assignment_ids']
        _require(_nonempty_list(ids) and all(type(i) is str for i in ids)
                 and len(ids) == len(set(ids)), 'gate_author_invalid')
        for identity in ids:
            actor = inputs.assignment(identity)
            _require(actor['role'] == 'owner' and actor['milestone'] == milestone, 'gate_author_invalid')
            authors.add(actor['actor_id'])
    except (KeyError, TypeError, ValueError):
        reasons.append('gate_author_invalid')
    expected_roles = {'source', 'integrity'} if milestone == 'M3' and gate['kind'] == 'finalization' else _ROLES[milestone]
    roles = gate['required_roles']
    if type(roles) is not dict or set(roles) != expected_roles:
        reasons.append('required_role_missing')
        roles = {role: value for role, value in roles.items() if type(role) is str} if type(roles) is dict else {}
    for role in sorted(roles):
        try:
            actor = inputs.assignment(roles[role])
            _require(actor['role'] == 'resolver' and actor['milestone'] == milestone
                     and actor['actor_id'] not in authors | reviewer_actors
                     and actor['id'] not in reviewer_ids, 'required_role_invalid')
            reviewer_ids.add(actor['id'])
            reviewer_actors.add(actor['actor_id'])
        except (KeyError, TypeError, ValueError):
            reasons.append('required_role_invalid')

    for field, label in [('source_refs', 'source'), ('approval_refs', 'approval')]:
        refs = gate[field]
        if not _nonempty_list(refs):
            reasons.append(f'{label}_missing')
            continue
        for ref in refs:
            try:
                if label == 'approval':
                    _approval(inputs, ref, gate['input_binding'])
                else:
                    _require(bool(inputs.reference(ref)), 'source_invalid')
            except (KeyError, TypeError, ValueError, StopIteration) as error:
                reasons.append('approval_not_current' if str(error) == 'approval_not_current' else f'{label}_invalid')

    decision = None
    try:
        decision = inputs.reference(gate['decision_ref'], 'decisions', 'Decision')
        reasons.extend(error['code'] for error in validate_rationale_links(snapshot, decision))
        _require(bool(decision['claim_dispositions']), 'decision_invalid')
    except (KeyError, TypeError, ValueError):
        reasons.append('decision_invalid')
    submitted, opposed_issue_ids = set(), set()
    submissions = gate['submission_refs']
    if not _nonempty_list(submissions):
        reasons.append('required_submission_missing')
    else:
        for ref in submissions:
            try:
                position = inputs.reference(ref, 'positions', 'Position')
                _require(position['input_binding'] == gate['input_binding'] and decision is not None
                         and ref in decision['position_refs'], 'required_submission_invalid')
                submitted.add(position['assignment_id'])
                if position['assignment_id'] in reviewer_ids and position['stance'] == 'oppose':
                    opposed_issue_ids.add(position['issue_id'])
            except (KeyError, TypeError, ValueError):
                reasons.append('required_submission_invalid')
        if not reviewer_ids <= submitted:
            reasons.append('required_submission_missing')

    scope = {'kind': gate['kind'], 'milestone': milestone, 'target_id': gate['target_id']}
    bound_revise, revise_unresolved = False, False
    try:
        issues = inputs.state.get('issues', {})
        _require(type(issues) is dict, 'issue_history_invalid')
        for identity in sorted(issues):
            issue = inputs.registered('issues', identity, 'Issue')
            scoped = scope in issue['blocking_scope']
            if issue['origin']['milestone'] != milestone and not scoped and identity not in opposed_issue_ids:
                continue
            status, latest = _status(inputs, issue)
            if status != 'resolved':
                unresolved.append(identity)
                if (identity in opposed_issue_ids and issue['severity'] != 'optional'
                        and not issue['blocking_scope']):
                    reasons.append('opposition_binding_missing')
            if decision and identity in decision['issue_ids'] and scoped and issue['resolution_condition']:
                bound_revise = True
                revise_unresolved |= status != 'resolved'
            if not scoped or issue['severity'] == 'optional' or status == 'resolved':
                continue
            if (milestone == 'M1' and gate['kind'] == 'handoff' and issue['category'] == 'empirical'
                    and status == 'transferred'):
                try:
                    _accepted_transfer(inputs, issue, latest)
                    continue
                except (KeyError, TypeError, ValueError, StopIteration) as error:
                    reasons.append(str(error) if str(error) in ('transfer_acceptance_invalid', 'transfer_acceptance_stale')
                                   else 'transfer_acceptance_invalid')
            reasons.append('blocking_issue_unresolved')
    except (KeyError, TypeError, ValueError):
        reasons.append('issue_history_invalid')
    if decision and decision['next_action']['kind'] == 'revise':
        if not bound_revise:
            reasons.append('revise_binding_missing')
        elif revise_unresolved:
            reasons.append('revision_required')
    return _result(reasons, unresolved)
