"""Bounded M1 node authorship and review linkage; no approval authority."""
from copy import deepcopy

from . import store
from .contracts import _COMMON
from .councils import (_common, _context as council_context, _fresh_ids, _valid,
                      _COUNCIL_FIELDS, _disclosed, _record_ref, _session, _submissions, reviewer_packet)
from .dependencies import _node
from .gates import _status
from .issues import _require

_FIELDS = set(_COMMON) | {'node', 'attempt', 'previous_ref_key', 'input_refs', 'content', 'revision_reason'}
_PARENTS = {'scope': (), 'questions': ('scope',), 'search': ('scope', 'questions'),
            'screen': ('scope', 'questions', 'search'), 'collect': ('screen',), 'extract': ('screen', 'collect'),
            'synthesize': ('screen', 'collect', 'extract'),
            'hypothesize': ('screen', 'extract', 'synthesize'),
            'review': ('screen', 'extract', 'synthesize', 'hypothesize')}
_NEXT = {'scope': 'questions', 'questions': 'search', 'search': 'screen', 'screen': 'collect', 'collect': 'extract', 'extract': 'synthesize',
         'synthesize': 'hypothesize', 'hypothesize': 'review', 'review': 'handoff'}
_CONTENT = {'scope': {'user_goal': 'text', 'user_constraints': ('array', 'text'), 'agent_assumptions': ('array', 'text')},
            'questions': {'questions': ('array', {'question': 'text', 'rationale': 'text'}),
                          'agent_assumptions': ('array', 'text')},
            'search': {key: ('array', 'text') for key in ('queries', 'sources', 'inclusion_criteria', 'exclusion_criteria')},
            'screen': {
                'search_log': ('array', {'search_id': 'text', 'query': 'text', 'source': 'text',
                                         'searched_at': 'text', 'result_count': 'text'}),
                'candidates': ('array', {'source_id': 'text', 'title': 'text',
                    'doi': ('nullable', 'text'), 'arxiv_id': ('nullable', 'text'), 'url': ('nullable', 'text'),
                    'source_type': 'text', 'access_status': ('enum', ('full_text', 'abstract', 'metadata_only', 'unavailable')),
                    'search_ids': ('array', 'text'), 'stance': ('enum', ('support', 'oppose', 'neutral', 'unknown'))}),
                'decisions': ('array', {'source_id': 'text', 'decision': ('enum', ('include', 'exclude')), 'reason': 'text'})}}
_ROLES = {'domain', 'methodology', 'critical'}


def _context(snapshot):
    inputs = council_context(snapshot)
    _require(all(type(record['state'].get(name, {})) is dict for _, record in inputs.history
                 for name in ('m1_node_revisions', 'm1_node_heads', 'imported_issue_states')),
             'm1_node_collection_invalid')
    return inputs


def _native(inputs, collection, record, event_type, payload):
    first = next(old for _, old in inputs.history if record['id'] in old['state'].get(collection, {}))
    event = first['events'][-1]
    actual = {key: value for key, value in event['payload'].items() if key != '_command_request'}
    _require(first['state'][collection][record['id']] == record
             and event['type'] == event_type and actual == payload, 'm1_native_record_invalid')
    return first


def _content_shape(node, content):
    if node in ('synthesize', 'hypothesize', 'review'):
        from .m1_review import content_shape
        return content_shape(node, content)
    if node in ('collect', 'extract'):
        from .m1_evidence import content_shape
        return content_shape(node, content)
    if node == 'screen':
        if (type(content) is not dict or type(content.get('search_log')) is not list
                or any(type(row) is not dict or type(row.get('result_count')) is not int
                       or row['result_count'] < 0 for row in content['search_log'])):
            return False
        # The common closed-schema checker has no integer spec; validate count
        # above, then adapt only its checked value for remaining field checks.
        content = {**content, 'search_log': [{**row, 'result_count': str(row['result_count'])}
                                           for row in content['search_log']]}
    return _valid(_CONTENT[node], content)


def _shape(record, project):
    return (_common(record, _FIELDS, project) and type(record['node']) is str and record['node'] in _PARENTS
            and _valid('uuid', record['attempt']) and type(record['input_refs']) is dict
            and set(record['input_refs']) == set(_PARENTS[record['node']])
            and _content_shape(record['node'], record['content'])
            and (record['node'] != 'questions' or bool(record['content']['questions'])))


def _node_identity(inputs, node_id):
    """Read the current revision identity without requiring its old inputs current."""
    _require(type(node_id) is str and node_id in _PARENTS, 'm1_node_invalid')
    identity = inputs.state.get('m1_node_heads', {}).get(node_id)
    _require(type(identity) is str, 'm1_node_missing')
    record = inputs.registered('m1_node_revisions', identity)
    _require(_shape(record, inputs.project) and record['node'] == node_id, 'm1_node_invalid')
    _native(inputs, 'm1_node_revisions', record, 'm1_node_registered',
            {'node': node_id, 'revision_id': identity, 'attempt': record['attempt']})
    head = next(head for head, old in inputs.history if old['state'].get('m1_node_revisions', {}).get(identity) == record)
    ref = dict(project_id=inputs.project, head_id=head, artifact_id=f'm1/nodes/{node_id}',
               sha256=store._hash(store._canonical(record)))
    inputs.reference(ref)
    return record, ref


def current_node(inputs, node_id):
    """Read the actual current node, requiring its consumed inputs current."""
    record, ref = _node_identity(inputs, node_id)
    for source in [*record['input_refs'].values(), *record['observation_refs']]:
        inputs.reference(source)
    return record, ref


def register_node(snapshot: dict, payload: dict) -> dict:
    """Register closed scope/questions/search/screen output as a fresh revision."""
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'artifact'} and type(payload['artifact']) is dict,
             'm1_node_invalid')
    artifact = deepcopy(payload['artifact'])
    _require(set(artifact) == (_FIELDS - {'previous_ref_key'}) | {'previous_ref'}, 'm1_node_invalid')
    previous = artifact.pop('previous_ref')
    artifact['previous_ref_key'] = store._canonical(previous).decode() if previous is not None else None
    _require(_shape(artifact, inputs.project), 'm1_node_invalid')
    node = artifact['node']
    _fresh_ids(inputs, [artifact['id']])
    old_records = inputs.state.get('m1_node_revisions', {}).values()
    _require(all(type(old) is dict and old.get('attempt') != artifact['attempt']
                 and old.get('event_id') != artifact['event_id'] for old in old_records), 'm1_revision_invalid')
    if node in inputs.state.get('m1_node_heads', {}):
        predecessor, current = _node_identity(inputs, node)
        _require(type(previous) is dict and previous == current and _valid('text', artifact['revision_reason']),
                 'm1_revision_invalid')
        if node in ('collect', 'extract'):
            from .m1_evidence import require_mismatch_publication
            require_mismatch_publication(snapshot, node)
        # Repair may replace an invalid council setup. Preserve native disclosed
        # proposals without requiring that predecessor's review policy to pass.
        for identity, declared in inputs.state.get('councils', {}).items():
            if (type(declared) is dict and declared.get('milestone') == 'M1'
                    and declared.get('node') == node and declared.get('attempt') == predecessor['attempt']):
                prior_council = inputs.registered('councils', identity)
                _require(_common(prior_council, _COUNCIL_FIELDS, inputs.project), 'm1_council_invalid')
                _native(inputs, 'councils', prior_council, 'council_prepared',
                        {'council_id': identity, 'session_id': prior_council['session_id']})
                _require(not _unpublished_proposals(inputs, prior_council), 'm1_issue_publication_required')
    else:
        _require(previous is None and artifact['revision_reason'] is None, 'm1_revision_invalid')
    for parent, ref in artifact['input_refs'].items():
        inputs.reference(ref)
        _, expected = current_node(inputs, parent)
        _require(_node(ref) == _node(expected), 'm1_node_input_invalid')
        # Authorship repairs remain possible while carried issues/reviews await
        # handling; projection still requires every final council.
        if parent not in ('synthesize', 'hypothesize', 'review'):
            _require(review_node(snapshot, parent)['ready'], 'm1_upstream_review_required')
    for ref in artifact['observation_refs']:
        inputs.reference(ref)
    extra_objects = {}
    if node in ('synthesize', 'hypothesize', 'review'):
        from .m1_review import validate_content
        validate_content(snapshot, inputs, artifact)
    if node in ('collect', 'extract'):
        from .m1_evidence import validate_content
        extra_objects = validate_content(snapshot, inputs, artifact)
    if node in ('search', 'screen'):
        from .m1_search import validate_search_content
        validate_search_content(inputs, artifact)
    return {'state_patch': {
        'm1_node_revisions': {**inputs.state.get('m1_node_revisions', {}), artifact['id']: artifact},
        'm1_node_heads': {**inputs.state.get('m1_node_heads', {}), node: artifact['id']}},
        'event': {**store._VERSION, 'type': 'm1_node_registered',
                  'payload': {'node': node, 'revision_id': artifact['id'], 'attempt': artifact['attempt']}},
        'object_inputs': {f'm1/nodes/{node}': store._canonical(artifact), **extra_objects}}


def _council(inputs, artifact, ref):
    matches = []
    for identity in inputs.state.get('councils', {}):
        council = inputs.registered('councils', identity)
        _require(_common(council, _COUNCIL_FIELDS, inputs.project), 'm1_council_invalid')
        if council['milestone'] == 'M1' and council['node'] == artifact['node'] and council['attempt'] == artifact['attempt']:
            matches.append(council)
    _require(len(matches) <= 1, 'm1_council_ambiguous')
    if not matches:
        return None
    council = matches[0]
    prepared = _native(inputs, 'councils', council, 'council_prepared',
                       {'council_id': council['id'], 'session_id': council['session_id']})
    session = _session(inputs, council)
    _require(_node(session['input_binding']) == _node(ref), 'm1_council_binding_invalid')
    _require(set(council['required_roles']) == _ROLES
             and set(council['required_roles'].values()) == set(session['participant_assignment_ids']), 'm1_council_roles_invalid')
    authors = [inputs.assignment(identity) for identity in council['author_assignment_ids']]
    reviewers = [inputs.assignment(identity) for identity in council['required_roles'].values()]
    _require(bool(authors) and all(a['milestone'] == 'M1' and a['role'] == 'owner' for a in authors)
             and {a['actor_id'] for a in authors} == {artifact['producer_id']}, 'm1_council_author_mismatch')
    _require(len(reviewers) == len({a['id'] for a in reviewers}) == len({a['actor_id'] for a in reviewers}) == 3
             and all(a['milestone'] == 'M1' and a['role'] == 'resolver' and a['actor_id'] != artifact['producer_id']
                     for a in reviewers), 'm1_council_independence_invalid')
    _require(all(prepared['state']['assignments'].get(a['id']) == a for a in [*authors, *reviewers])
             and prepared['state']['review_sessions'].get(session['id']) == session, 'm1_council_binding_invalid')
    return council


def _bound_refs(inputs, values):
    for ref in values:
        inputs.reference(ref, 'council_submissions')
    return {_node(ref) for ref in values}


def _unpublished_proposals(inputs, council):
    """Require publication while old targets are still current, without rereview."""
    records = _submissions(inputs, council)
    disclosed = _disclosed(inputs, council, records)
    unpublished = set()
    for phase in ('initial', 'response'):
        for item in disclosed[phase]:
            record = item['submission']
            _native(inputs, 'council_submissions', record, 'council_submission_registered',
                    {'submission_id': record['id'], 'session_id': council['session_id'], 'phase': phase})
            for proposal in record['issue_proposals']:
                if proposal['severity'] == 'optional':
                    continue
                if inputs.state.get('issues', {}).get(proposal['id']) != proposal:
                    unpublished.add(proposal['id'])
                else:
                    issue = inputs.registered('issues', proposal['id'], 'Issue')
                    _status(inputs, issue)
    return unpublished


def _judgments(inputs, council, records, reasons):
    expected_initials = {_node(_record_ref(inputs, 'council_submissions', record)) for record in records['initial'].values()}
    expected_responses = {_node(_record_ref(inputs, 'council_submissions', record)) for record in records['response'].values()}
    for actor, final in records['final'].items():
        if not expected_initials <= _bound_refs(inputs, records['response'][actor]['response_refs']):
            reasons.append('council_response_binding_missing')
        if not expected_responses <= _bound_refs(inputs, final['response_refs']):
            reasons.append('council_final_binding_missing')
        prior_issues = {position['issue_id'] for phase in ('initial', 'response')
                        for position in records[phase][actor]['positions']}
        positions = [*final['positions'], *(inputs.reference(ref, 'positions', 'Position')
                                           for ref in final['retained_position_refs'])]
        _require(all(position['assignment_id'] == actor and position['session_id'] == council['session_id']
                     and position['input_binding'] == final['input_binding'] for position in positions),
                 'm1_final_position_invalid')
        if not prior_issues <= {position['issue_id'] for position in positions}:
            reasons.append('council_final_position_missing')
        if final['recommendation'] == 'revise':
            reasons.append('revision_required')
        elif final['recommendation'] == 'defer':
            reasons.append('awaiting_input')
        else:
            _require(final['recommendation'] in ('ready', 'ready_with_limits'), 'm1_final_judgment_invalid')


def review_node(snapshot: dict, node_id: str) -> dict:
    """Pure current-node review readiness, never approval or execution readiness."""
    if node_id in ('collect', 'extract'):
        from .m1_evidence import prepare_evidence_check
        return prepare_evidence_check(snapshot, node_id=node_id)
    inputs = _context(snapshot)
    artifact, ref = current_node(inputs, node_id)
    reasons, unresolved, unpublished = [], set(), set()
    for parent, source in artifact['input_refs'].items():
        _, expected = current_node(inputs, parent)
        _require(_node(source) == _node(expected), 'm1_node_input_invalid')
        if not review_node(snapshot, parent)['ready']:
            reasons.append('upstream_review_required')
    council = _council(inputs, artifact, ref)
    phase = 'awaiting_council'
    if council is None:
        reasons.append('council_required')
    else:
        packet = reviewer_packet(snapshot, next(iter(council['required_roles'].values())))
        phase = packet['phase'].removesuffix('_wait')
        records = _submissions(inputs, council)
        for phase_records in records.values():
            for record in phase_records.values():
                _native(inputs, 'council_submissions', record, 'council_submission_registered',
                        {'submission_id': record['id'], 'session_id': council['session_id'], 'phase': record['phase']})
                actor = inputs.assignment(record['assignment_id'])
                _require(record['producer_id'] == actor['actor_id'] and record['input_binding'] == packet['input_binding'],
                         'm1_council_binding_invalid')
        if phase != 'complete':
            reasons.append(f'council_{phase}_required')
        else:
            _judgments(inputs, council, records, reasons)
        for disclosed in (packet['disclosed_initials'], packet['disclosed_responses']):
            for item in disclosed:
                for proposal in item['submission']['issue_proposals']:
                    if proposal['severity'] != 'optional' and inputs.state.get('issues', {}).get(proposal['id']) != proposal:
                        unpublished.add(proposal['id'])
        if unpublished:
            reasons.append('issue_publication_required')
    for identity in inputs.state.get('issues', {}):
        issue = inputs.registered('issues', identity, 'Issue')
        relevant = (issue['origin']['milestone'] == 'M1' and issue['origin']['node'] == node_id)
        scoped = {'kind': 'node', 'milestone': 'M1', 'target_id': node_id} in issue['blocking_scope']
        if not relevant and not scoped:
            continue
        status, _ = _status(inputs, issue)
        if status != 'resolved':
            unresolved.add(identity)
            if scoped and issue['severity'] != 'optional':
                reasons.append('blocking_issue_unresolved')
    reasons = list(dict.fromkeys(reasons))
    if node_id == 'screen':
        from .m1_search import opposing_exclusions
        if opposing_exclusions(inputs, artifact, ref):
            reasons.append('opposing_exclusion_issue_required')
    return deepcopy(dict(ready=not reasons, reason_codes=reasons,
        required_actions=[f'Address {reason} before advancing this node.' for reason in reasons], node_ref=ref,
        council_binding=dict(milestone='M1', node=node_id, attempt=artifact['attempt'], input_binding=ref,
                             author_actor_id=artifact['producer_id'], required_roles=sorted(_ROLES)),
        council_id=council['id'] if council else None, phase=phase,
        unresolved_issue_ids=sorted(unresolved), unpublished_issue_ids=sorted(unpublished),
        next_node=_NEXT[node_id] if not reasons else None, content=artifact['content']))
