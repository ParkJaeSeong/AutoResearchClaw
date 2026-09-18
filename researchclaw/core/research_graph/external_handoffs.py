"""Atlas-backed handoff manifests; shared receiver and issue policy stays in handoffs."""
from . import store
from .contracts import validate_record
from .councils import _record_ref
from .external_evidence import _resolve_record
from .issues import _require
from .m1_external_inputs import external_evidence, uses_external
from .m1_nodes import current_node, _council
from .work_accounting import identity

NODES = ('scope', 'questions', 'synthesize', 'hypothesize', 'review')
PROFILE = 'external_m1_handoff'
PROFILE_FIELDS = {'id', 'project_id', 'milestone', 'kind', 'target_id', 'profile',
                  'input_binding', 'basis_ref', 'preparation_ref'}


def is_external(inputs):
    return ('review' in inputs.state.get('m1_node_heads', {})
            and uses_external(current_node(inputs, 'review')[0]))


def preparation(snapshot, inputs, *, check_ready=True):
    from .m1_preparation import preparation_records, preparation_status, COLLECTION
    records = preparation_records(snapshot)
    _require(bool(records), 'preparation_required')
    record = records[-1]
    ref = _record_ref(inputs, COLLECTION, record)
    _require(record['review_ref'] == current_node(inputs, 'review')[1], 'preparation_review_invalid')
    if check_ready:
        status = preparation_status(snapshot, record)
        _require(status['current'] and status['preparation_ready'],
                 status['reason_codes'][0] if status['reason_codes'] else 'preparation_required')
    return record, ref


def route_evidence(snapshot, inputs, *, check_ready=True):
    artifact, _ = current_node(inputs, 'review')
    evidence = external_evidence(snapshot, artifact)
    preparation(snapshot, inputs, check_ready=check_ready)
    return evidence


def build(snapshot, publication, supplied_review, *, check_policy=True):
    from .handoffs import _context, _eligibility, _budget
    from .m1_review import _prior_issues
    if check_policy:
        inputs, artifact, ref, review, evidence, _, eligible = _eligibility(snapshot)
        owner = _budget(snapshot, inputs, ref, publication)
    else:
        inputs = _context(snapshot)
        artifact, ref = current_node(inputs, 'review')
        evidence = route_evidence(snapshot, inputs, check_ready=False)
        unresolved = [r['issue_id'] for r in _prior_issues(inputs) if r['native_status'] != 'resolved']
        eligible = sorted(r['issue_id'] for r in artifact['content']['prior_issue_dispositions']
                          if r['disposition'] == 'transfer_proposed' and r['issue_id'] in unresolved)
        limits = [*evidence['limitations'], *(limit for node in ('synthesize', 'hypothesize', 'review')
                  for limit in current_node(inputs, node)[0]['content']['limitations'])]
        review = dict(unresolved_issue_ids=unresolved, limitations=list(dict.fromkeys(limits)))
        council = _council(inputs, artifact, ref)
        owner = inputs.assignment(council['author_assignment_ids'][0])
    _require(supplied_review == ref, 'stale_handoff')
    _require(publication['producer_id'] == owner['actor_id'], 'handoff_author_invalid')
    prepared, preparation_ref = preparation(snapshot, inputs, check_ready=check_policy)
    basis = _resolve_record(inputs, evidence['basis_ref'], 'm1_evidence_bases', 'handoff_evidence_required', current=True)
    node_refs = {node: current_node(inputs, node)[1] for node in NODES}
    # Deterministic order is part of receiving verification's exact input binding.
    sources = [evidence['basis_ref'], *basis['review_refs'],
               *(claim['evidence_ref'] for claim in basis['claims']),
               *evidence['extraction_refs'].values(), preparation_ref,
               *prepared['decision_refs'].values(),
               *(ref for item in prepared['items'].values() for ref in item['verification_refs'])]
    source_refs = list({store._canonical(ref): ref for ref in sources}.values())
    for source in source_refs:
        inputs.reference(source)
    receiver_id = identity(publication['id'], 'receiver')
    proposals = [dict(issue_id=issue_id, to_milestone='M2', owner_assignment_id=receiver_id,
        verification_id=identity(publication['id'], f'verification:{issue_id}'),
        resolution_condition=inputs.state['issues'][issue_id]['resolution_condition'], acceptance_event_id=None)
        for issue_id in eligible]
    preparation_limits = []
    for decision_ref in prepared['decision_refs'].values():
        decision = _resolve_record(inputs, decision_ref, 'external_decisions',
                                   'preparation_decision_invalid', current=True)
        preparation_limits.extend(decision['limitations'])
    preparation_limits.extend(item['reason'] for item in prepared['items'].values()
                              if item['status'] == 'not_applicable')
    limitations = list(dict.fromkeys([*review['limitations'], *artifact['content']['limitations'],
                                     *preparation_limits]))
    handoff = {**publication, 'from_milestone': 'M1', 'to_milestone': 'M2', 'source_head': snapshot['id'],
        'artifact_refs': [*node_refs.values(), *source_refs], 'unresolved_issue_ids': review['unresolved_issue_ids'],
        'transfer_proposals': proposals, 'limitations': limitations, 'acceptance_ref': None}
    _require(not validate_record('Handoff', handoff), 'handoff_payload_invalid')
    manifest = dict(id=identity(publication['id'], 'manifest'), project_id=inputs.project, handoff_id=handoff['id'],
        route='external', node_refs=node_refs, basis_ref=evidence['basis_ref'], preparation_ref=preparation_ref,
        source_refs=source_refs, hypotheses=current_node(inputs, 'hypothesize')[0]['content']['hypotheses'],
        rejected_alternatives=current_node(inputs, 'synthesize')[0]['content']['rejected_alternatives'],
        prior_issue_dispositions=artifact['content']['prior_issue_dispositions'],
        open_questions=artifact['content']['open_questions'], limitations=limitations)
    gate = dict(id=identity(publication['id'], 'gate'), project_id=inputs.project, milestone='M1', kind='handoff',
        target_id='M2', profile=PROFILE, input_binding=ref, basis_ref=evidence['basis_ref'], preparation_ref=preparation_ref)
    return handoff, manifest, gate


def require_current(snapshot, inputs, manifest, gate):
    _require(is_external(inputs) and set(gate) == PROFILE_FIELDS, 'stale_handoff')
    evidence = route_evidence(snapshot, inputs)
    _, ref = preparation(snapshot, inputs)
    _require(evidence['basis_ref'] == gate['basis_ref'] == manifest['basis_ref']
             and ref == gate['preparation_ref'] == manifest['preparation_ref'], 'stale_handoff')
