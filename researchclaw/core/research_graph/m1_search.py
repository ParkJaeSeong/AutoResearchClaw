"""Native search/screen review and explicitly user-declared corpus authority."""
from copy import deepcopy
import json

from . import store
from .contracts import validate_record
from .councils import _fresh_ids, _record_ref, _valid
from .dependencies import _References, _key, _node
from .gates import _approval, _status
from .issues import _require
from .m1_nodes import _context, _native, _shape, current_node, review_node
from ..m1.literature import validate_literature, SEARCH, CANDIDATES, LOG, SHORTLIST, DECISIONS


def _rows(rows):
    return b'\n'.join(store._canonical(row) for row in rows)


def validate_search_content(inputs, artifact):
    """Use old M1 content validators without old-store writes or authority."""
    content = artifact['content']
    if artifact['node'] == 'search':
        _require(all(content.values()), 'm1_search_content_invalid')
        errors = validate_literature('search', {SEARCH: store._canonical(content)}, {})
    else:
        search, _ = current_node(inputs, 'search')
        candidates = [{key: value for key, value in row.items() if value is not None}
                      for row in content['candidates']]
        _require(all(row['search_ids'] and len(set(row['search_ids'])) == len(row['search_ids']) for row in candidates),
                 'm1_search_content_invalid')
        decisions = {row['source_id']: row for row in content['decisions']}
        _require(len(decisions) == len(content['decisions']) and set(decisions) == {row['source_id'] for row in candidates},
                 'm1_search_content_invalid')
        files = {SEARCH: store._canonical(search['content']), CANDIDATES: _rows(candidates),
                 LOG: _rows(content['search_log']), DECISIONS: _rows(content['decisions']),
                 SHORTLIST: _rows([{**row, **decisions[row['source_id']]} for row in candidates])}
        errors = (*validate_literature('collect', files, files), *validate_literature('screen', files, files))
    _require(not errors, 'm1_search_content_invalid')


def opposing_exclusions(inputs, artifact, ref):
    """Require explicit native source issues for declared opposing exclusions."""
    opposing = {source['source_id'] for source in artifact['content']['candidates'] if source['stance'] == 'oppose'}
    missing = {row['source_id'] for row in artifact['content']['decisions']
               if row['decision'] == 'exclude' and row['source_id'] in opposing}
    for identity in inputs.state.get('issues', {}):
        issue = inputs.registered('issues', identity, 'Issue')
        if (issue['category'] == 'source' and issue['severity'] != 'optional'
                and issue['origin']['milestone'] == 'M1' and issue['origin']['node'] == 'screen'
                and {'kind': 'node', 'milestone': 'M1', 'target_id': 'screen'} in issue['blocking_scope']
                and _node(ref) in {_node(target) for target in issue['target_refs']}):
            _status(inputs, issue)
            missing = {source for source in missing if issue['origin']['local_issue_id'] != f'opposing-exclusion/{source}'}
    return sorted(missing)


def _corpus_at(inputs, supplied):
    _References(inputs).resolve(supplied)
    _require(supplied['artifact_id'] == 'm1/nodes/screen', 'm1_corpus_invalid')
    artifact = json.loads(inputs.objects[supplied['sha256']])
    _require(_shape(artifact, inputs.project) and artifact['node'] == 'screen', 'm1_corpus_invalid')
    _require(inputs.registered('m1_node_revisions', artifact['id']) == artifact, 'm1_corpus_invalid')
    _native(inputs, 'm1_node_revisions', artifact, 'm1_node_registered',
            {'node': 'screen', 'revision_id': artifact['id'], 'attempt': artifact['attempt']})
    head = next(head for head, old in inputs.history if old['state'].get('m1_node_revisions', {}).get(artifact['id']) == artifact)
    ref = {**supplied, 'head_id': head}
    scope = sorted([*artifact['input_refs'].values(), ref], key=_key)
    for source in scope:
        _References(inputs).resolve(source)
    included = {row['source_id'] for row in artifact['content']['decisions'] if row['decision'] == 'include'}
    kept = sorted((source for source in artifact['content']['candidates'] if source['source_id'] in included), key=lambda s: s['source_id'])
    return dict(corpus_ref=ref, scope_refs=scope, kept_sources=kept)


def current_corpus(snapshot: dict) -> dict:
    inputs = _context(snapshot)
    _, ref = current_node(inputs, 'screen')
    return deepcopy(_corpus_at(inputs, ref))


def _receipt(inputs, identity):
    receipt = inputs.registered('approval_receipts', identity)
    _require(set(receipt) == {'id', 'project_id', 'producer_id', 'decision', 'binding', 'scope_refs'}
             and receipt['producer_id'] == 'user' and receipt['decision'] in ('approved', 'rejected'),
             'm1_corpus_receipt_invalid')
    first = next(old for _, old in inputs.history if identity in old['state'].get('approval_receipts', {}))
    event = first['events'][-1]
    payload = event['payload']
    _require(event['type'] == 'm1_corpus_decided' and _valid('text', payload.get('note')),
             'm1_corpus_receipt_invalid')
    _native(inputs, 'approval_receipts', receipt, 'm1_corpus_decided',
        {'receipt_id': identity, 'corpus_ref': receipt['binding'], 'decision': 'approve' if receipt['decision'] == 'approved' else 'reject',
         'note': payload['note'], 'actor': 'user'})
    return receipt


def _latest(inputs, corpus_ref):
    for event in reversed(inputs.history[-1][1]['events']):
        if event['type'] == 'm1_corpus_decided':
            receipt = _receipt(inputs, event['payload']['receipt_id'])
            if _node(receipt['binding']) == _node(corpus_ref):
                return receipt
    return None


def decide_corpus(snapshot: dict, payload: dict) -> dict:
    """Record only an explicit user-declared decision; not user authentication."""
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'receipt_id', 'corpus_ref', 'decision', 'note'}
             and _valid('uuid', payload['receipt_id']) and payload['decision'] in ('approve', 'reject')
             and _valid('text', payload['note']), 'm1_corpus_decision_invalid')
    _fresh_ids(inputs, [payload['receipt_id']])
    corpus = _corpus_at(inputs, payload['corpus_ref'])
    if payload['decision'] == 'approve':
        _require(corpus == current_corpus(snapshot), 'm1_corpus_changed')
        _require(review_node(snapshot, 'screen')['ready'], 'm1_corpus_review_required')
    receipt = dict(id=payload['receipt_id'], project_id=inputs.project, producer_id='user',
        decision='approved' if payload['decision'] == 'approve' else 'rejected',
        binding=corpus['corpus_ref'], scope_refs=corpus['scope_refs'])
    patch = {'approval_receipts': {**inputs.state.get('approval_receipts', {}), receipt['id']: receipt}}
    objects = {receipt['id']: store._canonical(receipt)}
    if payload['decision'] == 'reject':
        bindings = deepcopy(inputs.state.get('approval_bindings', {}))
        for identity in bindings:
            binding = inputs.registered('approval_bindings', identity, 'ApprovalBinding')
            if _node(binding['binding']) == _node(corpus['corpus_ref']):
                bindings[identity] = {**binding, 'validity': 'revoked'}
                objects[f'approval_bindings/{identity}'] = store._canonical(bindings[identity])
        patch['approval_bindings'] = bindings
    return {'state_patch': patch, 'object_inputs': objects,
        'event': {**store._VERSION, 'type': 'm1_corpus_decided', 'payload': {
            'receipt_id': receipt['id'], 'corpus_ref': corpus['corpus_ref'], 'decision': payload['decision'],
            'note': payload['note'], 'actor': 'user'}}}


def bind_corpus(snapshot: dict, payload: dict) -> dict:
    """Derive a binding from prior explicit authority, never create a decision."""
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'binding_id', 'event_id', 'receipt_ref'}
             and _valid('uuid', payload['binding_id']) and _valid('uuid', payload['event_id']), 'm1_corpus_binding_invalid')
    _fresh_ids(inputs, [payload['binding_id']])
    _References(inputs)  # Fail closed on malformed typed receipt collections.
    receipt = inputs.reference(payload['receipt_ref'], 'approval_receipts')
    _require(_receipt(inputs, receipt['id']) == receipt, 'm1_corpus_receipt_invalid')
    corpus = current_corpus(snapshot)
    _require(receipt['binding'] == corpus['corpus_ref'] and receipt['scope_refs'] == corpus['scope_refs'], 'm1_corpus_changed')
    _require(_latest(inputs, corpus['corpus_ref']) == receipt and receipt['decision'] == 'approved', 'm1_corpus_receipt_not_current')
    _require(review_node(snapshot, 'screen')['ready'], 'm1_corpus_review_required')
    binding = {**store._VERSION, 'id': payload['binding_id'], 'event_id': payload['event_id'], 'project_id': inputs.project,
        'producer_id': 'm1-corpus-approval-adapter', 'content_origin': inputs.state['content_origin'],
        'provenance_status': 'declared_only', 'observation_refs': [], 'existing_receipt_ref': payload['receipt_ref'],
        'binding': corpus['corpus_ref'], 'scope_refs': corpus['scope_refs'], 'validity': 'valid'}
    _require(not validate_record('ApprovalBinding', binding), 'm1_corpus_binding_invalid')
    return {'state_patch': {'approval_bindings': {**inputs.state.get('approval_bindings', {}), binding['id']: binding}},
        'object_inputs': {f"approval_bindings/{binding['id']}": store._canonical(binding)},
        'event': {**store._VERSION, 'type': 'm1_corpus_bound',
                  'payload': {'binding_id': binding['id'], 'receipt_ref': payload['receipt_ref']}}}


def corpus_status(snapshot: dict) -> dict:
    inputs = _context(snapshot)
    corpus = current_corpus(snapshot)
    latest = _latest(inputs, corpus['corpus_ref'])
    approval_ref = None
    if latest and latest['decision'] == 'approved':
        for identity in sorted(inputs.state.get('approval_bindings', {})):
            binding = inputs.registered('approval_bindings', identity, 'ApprovalBinding')
            if (binding['validity'] == 'valid' and binding['binding'] == corpus['corpus_ref']
                    and binding['existing_receipt_ref']['artifact_id'] == latest['id']):
                _native(inputs, 'approval_bindings', binding, 'm1_corpus_bound',
                        {'binding_id': identity, 'receipt_ref': binding['existing_receipt_ref']})
                candidate = _record_ref(inputs, 'approval_bindings', binding)
                _approval(inputs, candidate, corpus['corpus_ref'])
                _require(binding['scope_refs'] == corpus['scope_refs'], 'm1_corpus_binding_invalid')
                approval_ref = candidate
                break
    reasons = [] if approval_ref else ['corpus_rejected' if latest and latest['decision'] == 'rejected' else 'corpus_approval_required']
    return deepcopy({**corpus, 'approval_ref': approval_ref, 'approved': bool(approval_ref), 'reason_codes': reasons})


def prepare_search_council(snapshot: dict, *, node_id: str) -> dict:
    _require(node_id in ('search', 'screen'), 'm1_node_invalid')
    result = review_node(snapshot, node_id)
    if node_id == 'search':
        return result
    corpus = corpus_status(snapshot)
    reasons = list(dict.fromkeys([*result['reason_codes'], *corpus['reason_codes']]))
    return {**result, 'review_ready': result['ready'], 'ready': not reasons, 'reason_codes': reasons,
        'required_actions': [f'Address {reason} before extracting this corpus.' for reason in reasons],
        'next_node': result['next_node'] if not reasons else None,
        'corpus_ref': corpus['corpus_ref'], 'approval_ref': corpus['approval_ref'], 'approved': corpus['approved']}
