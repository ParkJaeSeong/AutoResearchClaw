"""Pure native M1 synthesis/hypothesis review; no scientific or transfer authority."""
from copy import copy, deepcopy
import json

from . import store
from .contracts import _REF, _REFS
from .councils import _valid
from .dependencies import _node
from .gates import _status
from .issues import _require

NODES = ('synthesize', 'hypothesize', 'review')
_TEXTS = ('array', 'text')
_CONTENT = {
    'synthesize': dict(findings=('array', dict(finding_id='text', claim='text', evidence_refs=_REFS,
        counterevidence_refs=_REFS, limitations=_TEXTS)), rejected_alternatives=('array', dict(
        alternative_id='text', description='text', reason='text', evidence_refs=_REFS)), limitations=_TEXTS),
    'hypothesize': dict(hypotheses=('array', dict(hypothesis_id='text', statement='text', population='text',
        prediction='text', falsification_condition='text', evidence_refs=_REFS, alternative_ids=_TEXTS,
        limitations=_TEXTS)), limitations=_TEXTS),
    'review': dict(prior_issue_dispositions=('array', dict(issue_id='uuid',
        disposition=('enum', ('carry_forward', 'verification_planned', 'native_resolved', 'transfer_proposed')),
        owner_assignment_id=('nullable', 'uuid'), hypothesis_ids=_TEXTS, rationale='text', verification_refs=_REFS)),
        open_questions=('array', dict(issue_id='uuid', question='text', method='text', resolution_condition='text',
            owner_assignment_id=('nullable', 'uuid'), to_milestone=('enum', ('M1', 'M2')),
            budget_ref=('nullable', _REF), limitations=_TEXTS)), limitations=_TEXTS)}


def content_shape(node, content):
    return _valid(_CONTENT[node], content)


def _unique(rows, key):
    _require(len(rows) == len({row[key] for row in rows}), 'm1_review_identity_invalid')


def _resolution(inputs, issue, refs):
    from .m1_nodes import _native
    status, event = _status(inputs, issue)
    _require(status == 'resolved' and event is not None and bool(refs)
             and refs == event['verification_refs'], 'm1_review_resolution_invalid')
    for ref in refs:
        result = inputs.reference(ref, 'verification_results', 'VerificationResult')
        # Native A05 result and its exact issue/rule binding; resolution itself
        # remains the existing independent A04 event, never a content assertion.
        _native(inputs, 'verification_results', result, 'verification_result_registered', result)
        verification = inputs.verification(result['verification_id'], issue['id'])
        _native(inputs, 'verifications', verification, 'verification_prepared', verification)
        _require(verification['acceptance_rule'] in result['checked_scope'], 'm1_review_resolution_invalid')


def validate_content(snapshot, inputs, artifact):
    from .m1_evidence import current_evidence
    from .m1_nodes import current_node
    evidence = current_evidence(snapshot)
    _require(evidence['ready'], 'm1_evidence_review_required')
    _require(artifact['input_refs']['screen'] == evidence['corpus_ref'], 'm1_review_corpus_invalid')
    allowed = {_node(ref) for ref in evidence['extraction_refs'].values()}
    node, content = artifact['node'], artifact['content']
    if node in ('synthesize', 'hypothesize'):
        rows, key = (content['findings'], 'finding_id') if node == 'synthesize' else (content['hypotheses'], 'hypothesis_id')
        _require(bool(rows), 'm1_review_content_missing'); _unique(rows, key)
        all_rows = [*rows, *content.get('rejected_alternatives', [])]
        for row in all_rows:
            _require(bool(row['evidence_refs']), 'm1_review_evidence_invalid')
            for ref in [*row['evidence_refs'], *row.get('counterevidence_refs', [])]:
                inputs.reference(ref)
                _require(_node(ref) in allowed, 'm1_review_evidence_invalid')
        if node == 'synthesize':
            _unique(content['rejected_alternatives'], 'alternative_id')
        else:
            synthesis = current_node(inputs, 'synthesize')[0]
            alternatives = {row['alternative_id'] for row in synthesis['content']['rejected_alternatives']}
            _require(all(set(row['alternative_ids']) <= alternatives for row in rows), 'm1_review_alternative_invalid')
        return
    hypotheses = {row['hypothesis_id'] for row in current_node(inputs, 'hypothesize')[0]['content']['hypotheses']}
    _unique(content['prior_issue_dispositions'], 'issue_id'); _unique(content['open_questions'], 'issue_id')
    dispositions = {row['issue_id']: row for row in content['prior_issue_dispositions']}
    for row in content['prior_issue_dispositions']:
        issue = inputs.registered('issues', row['issue_id'], 'Issue')
        _require(set(row['hypothesis_ids']) <= hypotheses, 'm1_review_hypothesis_invalid')
        if row['owner_assignment_id'] != _owner(inputs, issue):
            from .handoffs import accepted_owner_transition
            accepted_owner_transition(inputs, issue, row, artifact)
        if row['owner_assignment_id'] is not None:
            owner = inputs.assignment(row['owner_assignment_id'])
            _require(owner['role'] == 'owner' and owner['milestone'] == 'M1', 'm1_review_owner_invalid')
        for ref in row['verification_refs']:
            collection, kind = ('verifications', 'Verification') if ref['artifact_id'] in inputs.state.get('verifications', {}) else ('verification_results', 'VerificationResult')
            inputs.reference(ref, collection, kind)
        if row['disposition'] == 'native_resolved':
            _resolution(inputs, issue, row['verification_refs'])
        elif row['disposition'] == 'verification_planned':
            _require(bool(row['verification_refs']), 'm1_review_verification_missing')
            for ref in row['verification_refs']:
                verification = inputs.reference(ref, 'verifications', 'Verification')
                inputs.verification(verification['id'], issue['id'])
        elif row['disposition'] == 'transfer_proposed':
            _require(issue['category'] == 'empirical', 'm1_review_transfer_invalid')
    for row in content['open_questions']:
        issue = inputs.registered('issues', row['issue_id'], 'Issue')
        _require(row['issue_id'] in dispositions and row['question'] == issue['question']
                 and row['resolution_condition'] == issue['resolution_condition']
                 and row['owner_assignment_id'] == dispositions[issue['id']]['owner_assignment_id'], 'm1_review_question_invalid')
        if row['to_milestone'] == 'M2':
            _require(issue['category'] == 'empirical'
                     and dispositions[issue['id']]['disposition'] == 'transfer_proposed', 'm1_review_transfer_invalid')
        if row['budget_ref'] is not None:
            inputs.reference(row['budget_ref'])


def _imported_issues(inputs):
    """Reproduce A03 wrappers from the pinned archive, without materialization."""
    if not inputs.state.get('imported_issue_states'):
        return {}
    from .migration import _projection
    genesis = inputs.history[0][1]
    archive = genesis['state'].get('source_archive')
    _require(type(archive) is dict and genesis['events'][-1]['type'] == 'm1_imported',
             'm1_imported_issue_invalid')
    objects = {}
    for identity, digest in archive['commits'].items():
        objects[f'archive/commits/{identity}.json'] = inputs.objects[digest]
    for digest in archive['objects']:
        objects[f'archive/objects/{digest}'] = inputs.objects[digest]
    selected = json.loads(objects[f"archive/commits/{archive['head_id']}.json"])
    state, event = _projection(selected, archive['source_root'], archive['head_id'], archive['commits'], objects)
    _require(event == genesis['events'][-1] and all(state[key] == genesis['state'][key]
             for key in ('issues', 'imported_issue_states', 'source_archive'))
             and inputs.state.get('source_archive') == archive
             and inputs.state.get('imported_issue_states') == state['imported_issue_states'],
             'm1_imported_issue_invalid')
    _require(all(inputs.state['issues'].get(identity) == issue for identity, issue in state['issues'].items()),
             'm1_imported_issue_invalid')
    return state['issues']


def materialize_imported_issue(snapshot: dict, payload: dict) -> dict:
    """Explicitly back the unchanged A03 wrapper for subsequent native policy."""
    from .m1_nodes import _context
    _require(_valid({'issue_id': 'uuid'}, payload), 'm1_imported_issue_invalid')
    inputs = _context(snapshot)
    imported = _imported_issues(inputs)
    issue = imported.get(payload['issue_id'])
    _require(issue is not None, 'm1_imported_issue_invalid')
    identity = issue['id']
    _require(not any(identity in record['object_inputs'] for _, record in inputs.history),
             'm1_imported_issue_already_materialized')
    return dict(state_patch={}, event={**store._VERSION, 'type': 'import_issue_materialized',
        'payload': {'issue_id': identity}}, object_inputs={identity: store._canonical(issue)})


def _owner(inputs, issue):
    owner = issue['owner_assignment_id']
    for event in inputs.history[-1][1]['events']:
        if event['type'] == 'issue_event' and event['payload'].get('issue_id') == issue['id']:
            owner = event['payload'].get('owner_assignment_id', owner)
    return owner


def _prior_issues(inputs):
    from .m1_nodes import _native, _shape
    carried = set()
    for identity in inputs.state.get('m1_node_revisions', {}):
        record = inputs.registered('m1_node_revisions', identity)
        if record.get('node') != 'review':
            continue
        _require(_shape(record, inputs.project), 'm1_node_invalid')
        registered = _native(inputs, 'm1_node_revisions', record, 'm1_node_registered',
                dict(node='review', revision_id=identity, attempt=record['attempt']))
        historical = copy(inputs)
        historical.state = registered['state']
        end = next(index for index, (_, old) in enumerate(inputs.history) if old is registered)
        historical.history = inputs.history[:end + 1]
        carried.update(issue_id for issue_id, issue in historical.state.get('issues', {}).items()
                       if issue['origin']['milestone'] == 'M1' and _status(historical, issue)[0] != 'resolved')
        carried.update(row['issue_id'] for row in record['content']['prior_issue_dispositions'])
    rows = []
    imported = _imported_issues(inputs)
    # The imported review already carried these Issues, even when a native
    # check finishes before the first newly authored review revision.
    carried.update(imported)
    for identity in sorted(inputs.state.get('issues', {})):
        issue = imported[identity] if identity in imported else inputs.registered('issues', identity, 'Issue')
        status, _ = _status(inputs, issue)
        if identity not in carried and not (issue['origin']['milestone'] == 'M1' and status != 'resolved'):
            continue
        rows.append(dict(issue_id=identity, question=issue['question'], category=issue['category'],
            severity=issue['severity'], native_status=status, owner_assignment_id=_owner(inputs, issue),
            disposition=None))
    return rows


def prepare_hypothesis_review(snapshot: dict) -> dict:
    """Account for all carried issues before checking optional/missing new nodes."""
    from .m1_evidence import current_evidence
    from .m1_nodes import _context, current_node, review_node
    inputs = _context(snapshot)
    prior = _prior_issues(inputs)
    reasons, nodes, artifacts, limitations = [], dict.fromkeys(NODES), {}, []
    evidence = dict(corpus_ref=None, source_groups=None, limitations=[])
    try:
        evidence = current_evidence(snapshot)
        reasons.extend(evidence['reason_codes'])
    except ValueError as error:
        reasons.append(str(error))
    limitations.extend(evidence['limitations'])
    council_id, phase = None, 'awaiting_review'
    for node in NODES:
        try:
            artifact, ref = current_node(inputs, node)
            nodes[node], artifacts[node] = ref, artifact
            validate_content(snapshot, inputs, artifact)
            result = review_node(snapshot, node)
            reasons.extend(result['reason_codes'])
            limitations.extend(artifact['content']['limitations'])
            if node == 'review':
                council_id, phase = result['council_id'], result['phase']
                if council_id is not None:
                    council = inputs.registered('councils', council_id)
                    if not {row['issue_id'] for row in prior} <= set(council['issue_ids']):
                        reasons.append('prior_issue_review_binding_missing')
        except ValueError as error:
            code = str(error)
            if code == 'm1_node_missing':
                code = f'{node}_required'
            elif code == 'issue_reference_stale':
                code = f'{node}_stale'; nodes[node] = None; artifacts.pop(node, None)
            reasons.append(code)
    review = artifacts.get('review', {}).get('content', {})
    dispositions = {row['issue_id']: row for row in review.get('prior_issue_dispositions', [])}
    questions = {row['issue_id']: row for row in review.get('open_questions', [])}
    unaccounted, unresolved, transfers = [], [], []
    for row in prior:
        identity = row['issue_id']; disposition = dispositions.get(identity)
        if disposition is None:
            unaccounted.append(identity)
        else:
            row['disposition'] = disposition['disposition']
        if row['native_status'] != 'resolved':
            unresolved.append(identity)
            if row['owner_assignment_id'] is None:
                reasons.append('prior_issue_owner_missing')
            if disposition and disposition['disposition'] == 'transfer_proposed':
                question = questions.get(identity)
                if question is None or question['to_milestone'] != 'M2' or question['budget_ref'] is None:
                    reasons.append('transfer_plan_incomplete')
                transfers.append(dict(issue_id=identity, status='proposed', open_question=deepcopy(question)))
                reasons.append('transfer_acceptance_required')
            elif row['severity'] != 'optional':
                reasons.append('prior_issue_unresolved')
    if unaccounted:
        reasons.append('prior_issue_unaccounted')
    reasons = list(dict.fromkeys(reasons))
    return deepcopy(dict(ready=not reasons, reason_codes=reasons,
        required_actions=[f'Address {reason} before completing hypothesis review.' for reason in reasons],
        node_refs=nodes, corpus_ref=evidence['corpus_ref'], source_groups=evidence['source_groups'],
        prior_issues=prior, unaccounted_issue_ids=unaccounted, unresolved_issue_ids=unresolved,
        transfer_obligations=transfers, limitations=list(dict.fromkeys(limitations)), council_id=council_id, phase=phase))
