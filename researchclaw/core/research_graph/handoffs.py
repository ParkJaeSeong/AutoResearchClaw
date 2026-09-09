"""Native M1 handoff publication, explicit receiver acceptance, and pure gates.

Recorded eligibility is not scientific truth, execution permission, or M2 setup.
"""
from copy import deepcopy

from . import store
from .budgets import assess_next_work
from .contracts import _COMMON, _REF, _REFS, validate_record
from .councils import _common, _fresh_ids, _record_ref, _submissions, _valid
from .dependencies import _References, _node
from .gates import _accepted_transfer, _status
from .issues import _require
from .m1_nodes import _context as node_context, _council, _native, current_node, review_node, _assessment_snapshot
from .work_accounting import accounting_status, at, identity

_PROFILE_FIELDS = {'id', 'project_id', 'milestone', 'kind', 'target_id', 'profile', 'input_binding', 'corpus_ref', 'approval_ref'}
_ACCEPT_FIELDS = set(_COMMON) | {'handoff_ref', 'receiver_assignment_id', 'verification_refs', 'limitations'}
_COLLECTIONS = ('handoffs', 'handoff_manifests', 'handoff_receivers', 'handoff_acceptances', 'handoff_acceptance_ids',
                'transfer_acceptances', 'gate_requirements')
_NODES = ('scope', 'questions', 'search', 'screen', 'collect', 'extract', 'synthesize', 'hypothesize', 'review')


def _context(snapshot):
    inputs = node_context(snapshot)
    _require(all(type(old['state'].get(name, {})) is dict for _, old in inputs.history for name in _COLLECTIONS),
             'handoff_collection_invalid')
    return inputs


def _eligibility(snapshot):
    from .m1_evidence import current_evidence
    from .m1_review import prepare_hypothesis_review
    from .m1_search import corpus_status
    inputs = _context(snapshot)
    evidence, corpus = current_evidence(snapshot), corpus_status(snapshot)
    _require(evidence['ready'] and corpus['approved'], 'handoff_evidence_required')
    review = prepare_hypothesis_review(snapshot)
    artifact, review_ref = current_node(inputs, 'review')
    dispositions = {row['issue_id']: row for row in artifact['content']['prior_issue_dispositions']}
    questions = {row['issue_id']: row for row in artifact['content']['open_questions']}
    eligible = set()
    for issue_id in review['unresolved_issue_ids']:
        issue = inputs.registered('issues', issue_id, 'Issue')
        row, question = dispositions.get(issue_id), questions.get(issue_id)
        if issue['severity'] == 'optional' and (not row or row['disposition'] != 'transfer_proposed'):
            continue
        _require(issue['category'] == 'empirical' and row is not None and row['disposition'] == 'transfer_proposed'
                 and question is not None and question['to_milestone'] == 'M2' and question['budget_ref'] is not None,
                 'handoff_issue_unresolved')
        _require(_status(inputs, issue)[0] in ('open', 'transferred'), 'handoff_issue_status_invalid')
        eligible.add(issue_id)
    _require(set(review['unresolved_issue_ids']) <= set(questions), 'handoff_open_questions_required')
    deferred = {'transfer_acceptance_required', 'blocking_issue_unresolved', 'upstream_review_required'}
    remaining = [reason for reason in review['reason_codes'] if reason not in deferred]
    _require(not remaining, remaining[0] if remaining else 'handoff_review_required')
    # Every upstream node is checked separately. A generic upstream reason is
    # deferrable only after all concrete scoped blockers are proven empirical.
    for node in _NODES:
        result = review_node(snapshot, node)
        _require(not set(result['reason_codes']) - {'blocking_issue_unresolved', 'upstream_review_required'},
                 'handoff_review_required')
        for issue_id, issue in inputs.state.get('issues', {}).items():
            scope = dict(kind='node', milestone='M1', target_id=node)
            if scope in issue['blocking_scope'] and issue['severity'] != 'optional' and _status(inputs, issue)[0] != 'resolved':
                _require(issue_id in eligible, 'handoff_issue_unresolved')
        if node not in ('collect', 'extract'):
            record, ref = current_node(inputs, node)
            council = _council(inputs, record, ref)
            _require(council is not None and result['phase'] == 'complete', 'handoff_review_required')
            for final in _submissions(inputs, council)['final'].values():
                positions = [*final['positions'], *(inputs.reference(ref, 'positions', 'Position') for ref in final['retained_position_refs'])]
                for position in positions:
                    issue = inputs.registered('issues', position['issue_id'], 'Issue')
                    _require(not (position['stance'] == 'oppose' and issue['severity'] != 'optional'
                        and not issue['blocking_scope'] and _status(inputs, issue)[0] != 'resolved'), 'opposition_binding_missing')
    for issue_id, issue in inputs.state.get('issues', {}).items():
        scope = dict(kind='handoff', milestone='M1', target_id='M2')
        if scope in issue['blocking_scope'] and issue['severity'] != 'optional' and _status(inputs, issue)[0] != 'resolved':
            _require(issue_id in eligible, 'handoff_issue_unresolved')
    return inputs, artifact, review_ref, review, evidence, corpus, sorted(eligible)


def _budget(snapshot, inputs, review_ref, publication):
    status = accounting_status(snapshot)
    _require(status['ready'], status['reason_codes'][0] if status['reason_codes'] else 'work_accounting_required')
    record = current_node(inputs, 'review')[0]; council = _council(inputs, record, review_ref)
    owner = inputs.assignment(council['author_assignment_ids'][0])
    work = {**publication, 'assignment_id': owner['id'], 'milestone': 'M1', 'node': 'handoff',
        'question': 'Publish the reviewed M1 package', 'input_refs': [review_ref], 'work': 'Record M1 handoff',
        'acceptance_rule': 'The current evidence, independent review and explicit receiver obligations are bound'}
    result = assess_next_work(snapshot, dict(work=work,
        resource_request=dict(returns=0, verification_runs=0, estimated_cost=None, cost_status='unknown'),
        correction_ref=None, correction_approval_ref=None, semantic_status='literal_only', resume_ref=None))
    _require(result['ready'], result['reason_codes'][0] if result['reason_codes'] else 'handoff_budget_required')
    return owner


def _build(snapshot, publication, supplied_review, *, check_policy=True):
    if check_policy:
        inputs, artifact, ref, review, evidence, corpus, eligible = _eligibility(snapshot)
        owner = _budget(snapshot, inputs, ref, publication)
    else:
        # Reconstruct exact producer-derived bytes at the original ancestor.
        # Current policy is assessed separately; no stored readiness is trusted.
        from .m1_evidence import current_evidence
        from .m1_search import corpus_status
        from .m1_review import _prior_issues
        inputs = _context(snapshot); artifact, ref = current_node(inputs, 'review')
        evidence, corpus = current_evidence(snapshot), corpus_status(snapshot)
        prior = _prior_issues(inputs)
        unresolved = [row['issue_id'] for row in prior if row['native_status'] != 'resolved']
        eligible = sorted(row['issue_id'] for row in artifact['content']['prior_issue_dispositions']
                          if row['disposition'] == 'transfer_proposed' and row['issue_id'] in unresolved)
        limits = [*evidence['limitations'], *(limit for node in ('synthesize', 'hypothesize', 'review')
                  for limit in current_node(inputs, node)[0]['content']['limitations'])]
        review = dict(unresolved_issue_ids=unresolved, limitations=list(dict.fromkeys(limits)))
        council = _council(inputs, artifact, ref); owner = inputs.assignment(council['author_assignment_ids'][0])
    _require(supplied_review == ref, 'stale_handoff')
    _require(publication['producer_id'] == owner['actor_id'], 'handoff_author_invalid')
    node_refs = {node: current_node(inputs, node)[1] for node in _NODES}
    source_refs = []
    for row in evidence['collected_source_refs'].values():
        source_refs.extend(ref for ref in (row['metadata_ref'], row['raw_ref']) if ref is not None)
    source_refs.extend(evidence['extraction_refs'].values())
    source_refs = list({store._canonical(ref): ref for ref in source_refs}.values())
    receiver_id = identity(publication['id'], 'receiver')
    proposals = [dict(issue_id=issue_id, to_milestone='M2', owner_assignment_id=receiver_id,
        verification_id=identity(publication['id'], f'verification:{issue_id}'),
        resolution_condition=inputs.state['issues'][issue_id]['resolution_condition'], acceptance_event_id=None) for issue_id in eligible]
    limitations = list(dict.fromkeys([*review['limitations'], *artifact['content']['limitations']]))
    handoff = {**publication, 'from_milestone': 'M1', 'to_milestone': 'M2', 'source_head': snapshot['id'],
        'artifact_refs': [*node_refs.values(), *source_refs], 'unresolved_issue_ids': review['unresolved_issue_ids'],
        'transfer_proposals': proposals, 'limitations': limitations, 'acceptance_ref': None}
    _require(not validate_record('Handoff', handoff), 'handoff_payload_invalid')
    manifest = dict(id=identity(publication['id'], 'manifest'), project_id=inputs.project, handoff_id=handoff['id'],
        node_refs=node_refs, corpus_ref=corpus['corpus_ref'], source_refs=source_refs, source_groups=evidence['source_groups'],
        hypotheses=current_node(inputs, 'hypothesize')[0]['content']['hypotheses'],
        rejected_alternatives=current_node(inputs, 'synthesize')[0]['content']['rejected_alternatives'],
        prior_issue_dispositions=artifact['content']['prior_issue_dispositions'], open_questions=artifact['content']['open_questions'], limitations=limitations)
    gate = dict(id=identity(publication['id'], 'gate'), project_id=inputs.project, milestone='M1', kind='handoff', target_id='M2',
        profile='native_m1_handoff', input_binding=ref, corpus_ref=corpus['corpus_ref'], approval_ref=corpus['approval_ref'])
    return handoff, manifest, gate


def issue_handoff(snapshot: dict, payload: dict) -> dict:
    snapshot = _assessment_snapshot(snapshot)
    _require(type(payload) is dict and set(payload) == {'publication', 'review_ref'}
             and _common(payload['publication'], set(_COMMON), snapshot['state']['project_id'])
             and _valid(_REF, payload['review_ref']), 'handoff_payload_invalid')
    inputs = _context(snapshot); publication = payload['publication']
    _fresh_ids(inputs, [publication['id'], publication['event_id'], identity(publication['id'], 'manifest'),
                       identity(publication['id'], 'gate'), identity(publication['id'], 'receiver')])
    for ref in publication['observation_refs']:
        inputs.reference(ref)
    for manifest in inputs.state.get('handoff_manifests', {}).values():
        _require(_node(manifest['node_refs']['review']) != _node(payload['review_ref']), 'handoff_already_issued')
    handoff, manifest, gate = _build(snapshot, publication, payload['review_ref'])
    return dict(state_patch=dict(handoffs={**inputs.state.get('handoffs', {}), handoff['id']: handoff},
        handoff_manifests={**inputs.state.get('handoff_manifests', {}), manifest['id']: manifest},
        gate_requirements={**inputs.state.get('gate_requirements', {}), gate['id']: gate}),
        event={**store._VERSION, 'type': 'm1_handoff_issued', 'payload': dict(handoff_id=handoff['id'], review_ref=payload['review_ref'])},
        object_inputs={record['id']: store._canonical(record) for record in (handoff, manifest, gate)})


def _issued(inputs, handoff_id):
    handoff = inputs.registered('handoffs', handoff_id, 'Handoff')
    manifest = inputs.registered('handoff_manifests', identity(handoff_id, 'manifest'))
    gate = inputs.registered('gate_requirements', identity(handoff_id, 'gate'))
    first = _native(inputs, 'handoffs', handoff, 'm1_handoff_issued',
                    dict(handoff_id=handoff_id, review_ref=gate['input_binding']))
    index = next(index for index, (_, old) in enumerate(inputs.history) if old is first)
    _require(index > 0 and handoff['source_head'] == inputs.history[index - 1][0], 'handoff_native_invalid')
    publication = {key: handoff[key] for key in _COMMON}
    expected = _build(_assessment_snapshot(at(inputs, index - 1)), publication, gate['input_binding'], check_policy=False)
    _require((handoff, manifest, gate) == expected
             and first['state'].get('handoff_manifests', {}).get(manifest['id']) == manifest
             and first['state'].get('gate_requirements', {}).get(gate['id']) == gate, 'handoff_native_invalid')
    return handoff, manifest, gate


def _current(snapshot, inputs, handoff, manifest, gate):
    from .m1_search import corpus_status
    resolver = _References(inputs)
    try:
        _require(all(resolver.resolve(ref) for ref in handoff['artifact_refs']), 'stale_handoff')
        corpus = corpus_status(snapshot)
        _require(corpus['approved'] and corpus['corpus_ref'] == gate['corpus_ref']
                 and corpus['approval_ref'] == gate['approval_ref'], 'stale_handoff')
        _require(all(current_node(inputs, node)[1] == ref for node, ref in manifest['node_refs'].items()), 'stale_handoff')
    except ValueError as error:
        raise ValueError('stale_handoff') from error


def _receiver(inputs, handoff, manifest):
    receiver_id = identity(handoff['id'], 'receiver')
    setup = inputs.registered('handoff_receivers', identity(handoff['id'], 'receiver-setup'))
    assignment = inputs.assignment(receiver_id)
    expected = dict(id=identity(handoff['id'], 'receiver-setup'), project_id=inputs.project,
                    handoff_id=handoff['id'], assignment_id=receiver_id, producer_id=assignment['actor_id'])
    _require(setup == expected and assignment['role'] == 'owner' and assignment['milestone'] == 'M2'
             and assignment['actor_id'] != handoff['producer_id'], 'handoff_receiver_invalid')
    first = _native(inputs, 'handoff_receivers', setup, 'm1_handoff_receiver_assigned',
                    dict(handoff_id=handoff['id'], setup_id=setup['id']))
    _require(first['state']['assignments'].get(receiver_id) == assignment, 'handoff_receiver_invalid')
    return assignment


def assign_receiver(snapshot: dict, payload: dict) -> dict:
    snapshot = _assessment_snapshot(snapshot)
    from .councils import _ASSIGNMENT_FIELDS
    _require(type(payload) is dict and set(payload) == {'handoff_ref', 'assignment'} and _valid(_REF, payload['handoff_ref']),
             'handoff_receiver_invalid')
    inputs = _context(snapshot); handoff = inputs.reference(payload['handoff_ref'], 'handoffs', 'Handoff')
    handoff, manifest, gate = _issued(inputs, handoff['id']); _current(snapshot, inputs, handoff, manifest, gate)
    assignment = payload['assignment']; receiver_id = identity(handoff['id'], 'receiver')
    _require(type(assignment) is dict and set(assignment) == _ASSIGNMENT_FIELDS and assignment.get('id') == receiver_id
             and assignment.get('project_id') == inputs.project and assignment.get('role') == 'owner'
             and assignment.get('milestone') == 'M2' and assignment.get('active') is True
             and _valid('text', assignment.get('actor_id')) and assignment['actor_id'] != handoff['producer_id'], 'handoff_receiver_invalid')
    setup = dict(id=identity(handoff['id'], 'receiver-setup'), project_id=inputs.project, handoff_id=handoff['id'],
                 assignment_id=receiver_id, producer_id=assignment['actor_id'])
    _fresh_ids(inputs, [receiver_id, setup['id']])
    return dict(state_patch=dict(assignments={**inputs.state.get('assignments', {}), receiver_id: assignment},
        handoff_receivers={**inputs.state.get('handoff_receivers', {}), setup['id']: setup}),
        event={**store._VERSION, 'type': 'm1_handoff_receiver_assigned', 'payload': dict(handoff_id=handoff['id'], setup_id=setup['id'])},
        object_inputs={row['id']: store._canonical(row) for row in (assignment, setup)})


def _verification_inputs(inputs, handoff, manifest):
    return [_record_ref(inputs, 'handoffs', handoff), _record_ref(inputs, 'handoff_manifests', manifest), *handoff['artifact_refs']]


def _verifications(inputs, handoff, manifest, refs):
    _require(_valid(_REFS, refs) and len(refs) == len(handoff['transfer_proposals']), 'handoff_verification_invalid')
    by_id = {}
    questions = {row['issue_id']: row for row in manifest['open_questions']}
    for ref in refs:
        verification = inputs.reference(ref, 'verifications', 'Verification')
        _require(verification['id'] not in by_id, 'handoff_verification_invalid')
        _native(inputs, 'verifications', verification, 'verification_prepared', verification)
        by_id[verification['id']] = verification
    for proposal in handoff['transfer_proposals']:
        verification = by_id.get(proposal['verification_id']); issue = inputs.registered('issues', proposal['issue_id'], 'Issue')
        _require(verification is not None and verification['issue_ids'] == [issue['id']]
                 and verification['owner_assignment_id'] == proposal['owner_assignment_id']
                 and verification['question'] == issue['question'] and verification['acceptance_rule'] == issue['resolution_condition']
                 and verification['input_refs'] == _verification_inputs(inputs, handoff, manifest)
                 and verification['budget_ref'] == questions[issue['id']]['budget_ref'], 'handoff_verification_invalid')
        owner = inputs.assignment(proposal['owner_assignment_id'])
        _require(verification['producer_id'] == owner['actor_id'] and verification['method'] == 'experiment', 'handoff_verification_invalid')
        inputs.verification(verification['id'], issue['id'])


def _accepted(inputs, handoff, manifest):
    acceptance_id = inputs.state.get('handoff_acceptance_ids', {}).get(handoff['id'])
    if acceptance_id is None:
        return None
    acceptance = inputs.registered('handoff_acceptances', acceptance_id)
    _require(_common(acceptance, _ACCEPT_FIELDS, inputs.project), 'handoff_acceptance_invalid')
    receiver = _receiver(inputs, handoff, manifest)
    _require(acceptance['handoff_ref'] == _record_ref(inputs, 'handoffs', handoff)
             and acceptance['receiver_assignment_id'] == receiver['id'] and acceptance['producer_id'] == receiver['actor_id'],
             'handoff_acceptance_invalid')
    _verifications(inputs, handoff, manifest, acceptance['verification_refs'])
    first = _native(inputs, 'handoff_acceptances', acceptance, 'm1_handoff_accepted',
                    dict(handoff_id=handoff['id'], acceptance_id=acceptance_id))
    _require(first['state'].get('handoff_acceptance_ids', {}).get(handoff['id']) == acceptance_id, 'handoff_acceptance_invalid')
    for proposal in handoff['transfer_proposals']:
        expected = dict(id=identity(handoff['id'], f"acceptance:{proposal['issue_id']}"), project_id=inputs.project,
            issue_id=proposal['issue_id'], owner_assignment_id=receiver['id'], verification_id=proposal['verification_id'],
            to_milestone='M2', accepted=True, producer_id=receiver['actor_id'])
        _require(inputs.registered('transfer_acceptances', expected['id']) == expected
                 and first['state'].get('transfer_acceptances', {}).get(expected['id']) == expected,
                 'handoff_acceptance_invalid')
    return acceptance


def accept_handoff(snapshot: dict, payload: dict) -> dict:
    snapshot = _assessment_snapshot(snapshot)
    _require(type(payload) is dict and set(payload) == {'acceptance', 'handoff_ref', 'receiver_assignment_id', 'verification_refs', 'limitations'}
             and _common(payload['acceptance'], set(_COMMON), snapshot['state']['project_id'])
             and _valid(_REF, payload['handoff_ref']) and _valid('uuid', payload['receiver_assignment_id'])
             and _valid(_REFS, payload['verification_refs']) and _valid(('array', 'text'), payload['limitations']), 'handoff_payload_invalid')
    inputs = _context(snapshot); handoff = inputs.reference(payload['handoff_ref'], 'handoffs', 'Handoff')
    handoff, manifest, gate = _issued(inputs, handoff['id']); _current(snapshot, inputs, handoff, manifest, gate)
    receiver = _receiver(inputs, handoff, manifest)
    _require(payload['receiver_assignment_id'] == receiver['id'] and payload['acceptance']['producer_id'] == receiver['actor_id'],
             'handoff_receiver_invalid')
    _require(handoff['id'] not in inputs.state.get('handoff_acceptance_ids', {}), 'handoff_already_accepted')
    _verifications(inputs, handoff, manifest, payload['verification_refs'])
    _eligibility(snapshot)
    _require(accounting_status(snapshot)['ready'], 'work_ledger_refresh_required')
    acceptance = {**payload['acceptance'], **{key: payload[key] for key in ('handoff_ref', 'receiver_assignment_id', 'verification_refs', 'limitations')}}
    _require(acceptance['handoff_ref'] == _record_ref(inputs, 'handoffs', handoff), 'handoff_acceptance_invalid')
    transfers = [dict(id=identity(handoff['id'], f"acceptance:{proposal['issue_id']}"), project_id=inputs.project,
        issue_id=proposal['issue_id'], owner_assignment_id=receiver['id'], verification_id=proposal['verification_id'], to_milestone='M2',
        accepted=True, producer_id=receiver['actor_id']) for proposal in handoff['transfer_proposals']]
    _fresh_ids(inputs, [acceptance['id'], acceptance['event_id'], *(row['id'] for row in transfers)])
    for ref in acceptance['observation_refs']:
        inputs.reference(ref)
    return dict(state_patch=dict(handoff_acceptances={**inputs.state.get('handoff_acceptances', {}), acceptance['id']: acceptance},
        handoff_acceptance_ids={**inputs.state.get('handoff_acceptance_ids', {}), handoff['id']: acceptance['id']},
        transfer_acceptances={**inputs.state.get('transfer_acceptances', {}), **{row['id']: row for row in transfers}}),
        event={**store._VERSION, 'type': 'm1_handoff_accepted', 'payload': dict(handoff_id=handoff['id'], acceptance_id=acceptance['id'])},
        object_inputs={row['id']: store._canonical(row) for row in [acceptance, *transfers]})


def _transfer_event(inputs, handoff, manifest, proposal, event):
    disposition = next(row for row in manifest['prior_issue_dispositions'] if row['issue_id'] == proposal['issue_id'])
    m1_owner = inputs.assignment(disposition['owner_assignment_id'])
    _require(event is not None and m1_owner['role'] == 'owner' and m1_owner['milestone'] == 'M1'
             and event['actor_assignment_id'] == m1_owner['id'] and event['producer_id'] == m1_owner['actor_id'],
             'handoff_transfer_owner_invalid')
    _require(event['owner_assignment_id'] == proposal['owner_assignment_id']
             and event['verification_id'] == proposal['verification_id']
             and event['acceptance_event_id'] == identity(handoff['id'], f"acceptance:{proposal['issue_id']}"),
             'handoff_acceptance_invalid')


def accepted_owner_transition(inputs, issue, disposition, artifact):
    """Validate an immutable review's old M1 owner against its exact M2 transfer."""
    status, event = _status(inputs, issue)
    _require(disposition['disposition'] == 'transfer_proposed' and issue['category'] == 'empirical'
             and status == 'transferred', 'm1_review_owner_invalid')
    _accepted_transfer(inputs, issue, event)
    for handoff_id in inputs.state.get('handoffs', {}):
        handoff, manifest, gate = _issued(inputs, handoff_id)
        if gate['input_binding']['sha256'] != store._hash(store._canonical(artifact)):
            continue
        matching = next((row for row in manifest['prior_issue_dispositions'] if row['issue_id'] == issue['id']), None)
        proposal = next((row for row in handoff['transfer_proposals'] if row['issue_id'] == issue['id']), None)
        if matching == disposition and proposal is not None and _accepted(inputs, handoff, manifest) is not None:
            _transfer_event(inputs, handoff, manifest, proposal, event)
            return
    raise ValueError('m1_review_owner_invalid')


def handoff_status(snapshot: dict, *, handoff_id: str) -> dict:
    snapshot = _assessment_snapshot(snapshot)
    inputs = _context(snapshot); handoff, manifest, gate = _issued(inputs, handoff_id)
    reasons, accepted = [], None
    acceptance_id = inputs.state.get('handoff_acceptance_ids', {}).get(handoff_id)
    if acceptance_id is not None:
        index = next(index for index, (_, old) in enumerate(inputs.history)
                     if acceptance_id in old['state'].get('handoff_acceptances', {}))
        accepted = _accepted(_context(at(inputs, index)), handoff, manifest)
    try:
        _current(snapshot, inputs, handoff, manifest, gate)
        _eligibility(snapshot)
        accepted = _accepted(inputs, handoff, manifest)
        publication = {key: handoff[key] for key in _COMMON}
        _budget(snapshot, inputs, gate['input_binding'], publication)
        if accepted is None:
            reasons.append('handoff_acceptance_required')
        for proposal in handoff['transfer_proposals']:
            issue = inputs.registered('issues', proposal['issue_id'], 'Issue'); status, event = _status(inputs, issue)
            if status != 'transferred':
                reasons.append('native_transfer_required'); continue
            _accepted_transfer(inputs, issue, event)
            _require(accepted is not None, 'handoff_acceptance_invalid')
            _transfer_event(inputs, handoff, manifest, proposal, event)
    except ValueError as error:
        reasons.append(str(error))
    return deepcopy(dict(status='accepted' if accepted else 'issued_awaiting_acceptance', gate_ready=not reasons,
        reason_codes=list(dict.fromkeys(reasons)), required_actions=[f'Address {code} before completing handoff.' for code in dict.fromkeys(reasons)],
        handoff_ref=_record_ref(inputs, 'handoffs', handoff), gate_id=gate['id'], manifest=manifest,
        receiver_assignment_id=identity(handoff_id, 'receiver'), transfer_proposals=handoff['transfer_proposals'],
        transfer_acceptance_ids={row['issue_id']: identity(handoff_id, f"acceptance:{row['issue_id']}") for row in handoff['transfer_proposals']},
        verification_input_refs=_verification_inputs(inputs, handoff, manifest), unresolved_issue_ids=handoff['unresolved_issue_ids']))


def assess_native_handoff(snapshot: dict, gate: dict) -> dict:
    _require(set(gate) == _PROFILE_FIELDS and gate['profile'] == 'native_m1_handoff'
             and gate['milestone'] == 'M1' and gate['kind'] == 'handoff' and gate['target_id'] == 'M2', 'gate_invalid')
    inputs = _context(snapshot)
    matches = [identity_ for identity_ in inputs.state.get('handoffs', {}) if identity(identity_, 'gate') == gate['id']]
    _require(len(matches) == 1, 'handoff_native_invalid')
    result = handoff_status(snapshot, handoff_id=matches[0])
    return dict(ready=result['gate_ready'], reason_codes=result['reason_codes'], required_actions=result['required_actions'],
                unresolved_issue_ids=result['unresolved_issue_ids'])
