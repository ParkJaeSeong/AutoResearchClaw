"""Bounded native work recording and declared usage accounting; no execution."""
from copy import deepcopy
import json
from uuid import UUID, uuid5

from . import store
from .budgets import _ledger
from .return_policy import return_mode
from .councils import _COUNCIL_FIELDS, _common, _fresh_ids, _record_ref, _session, _submissions, _valid
from .dependencies import _References, _node
from .gates import _status
from .issues import _require
from .m1_nodes import _context as node_context, _council, _native, _node_identity, _shape

_COLLECTIONS = ('work_records', 'work_ledgers')


def identity(namespace, name):
    return str(uuid5(UUID(namespace), name))


def at(inputs, index):
    snapshot = store._receipt(*inputs.history[index])
    snapshot['_issue_context'] = dict(history=inputs.history[:index + 1], objects=inputs.objects)
    return snapshot


def _context(snapshot):
    inputs = node_context(snapshot)
    _require(all(type(old['state'].get(name, {})) is dict for _, old in inputs.history for name in _COLLECTIONS),
             'work_collection_invalid')
    return inputs


def _counts(inputs):
    revisions = inputs.state.get('m1_node_revisions', {})
    returns = 0
    for record in revisions.values():
        _require(_shape(record, inputs.project), 'work_source_invalid')
        _native(inputs, 'm1_node_revisions', record, 'm1_node_registered',
                dict(node=record['node'], revision_id=record['id'], attempt=record['attempt']))
        returns += record['previous_ref_key'] is not None
    for issue in inputs.state.get('issues', {}).values():
        _status(inputs, issue)
    begun = set()
    for event in inputs.history[-1][1]['events']:
        if event['type'] == 'issue_event' and event['payload']['to_status'] == 'checking':
            for ref in event['payload']['verification_refs']:
                verification = inputs.reference(ref, 'verifications', 'Verification')
                _native(inputs, 'verifications', verification, 'verification_prepared', verification)
                begun.add(verification['id'])
    return returns, begun


def _atlas_review_input(prior, source, session, author):
    """Authenticate the frozen Atlas review through its original import context."""
    from .external_evidence import _resolve_record, _authored, _REVIEW_FIELDS, record_review

    historical = _context(prior)
    review = _resolve_record(historical, session['input_binding'], 'external_reviews', 'work_source_invalid')
    _authored(historical, 'external_reviews', review, 'external_review_recorded')
    index = next(i for i, (_, old) in enumerate(historical.history)
                 if review['id'] in old['state'].get('external_reviews', {}))
    _require(index > 0, 'work_source_invalid')
    # Replays native import-byte, version, evidence and question checks where
    # the review was authored, rather than applying today's research context.
    replay = record_review(at(historical, index - 1), {key: review[key] for key in _REVIEW_FIELDS})
    _require(replay['state_patch']['external_reviews'][review['id']] == review
             and review['producer_id'] == author['actor_id'] == source['producer_id'], 'work_source_invalid')
    expected = {store._canonical(review[key]) for key in ('evidence_ref', 'question_ref')}
    _require({store._canonical(ref) for ref in source['allowed_evidence_refs']} == expected,
             'work_source_invalid')


def _non_node_council(inputs, source, record_id):
    """Account explicit native preparation reviews, without inventing M1 nodes."""
    from .councils import prepare_council, register_submission
    from .issue_scopes import _proposal
    from .source_intake import captured_records

    _require(_common(source, _COUNCIL_FIELDS, inputs.project)
             and source['milestone'] == 'M1', 'work_source_invalid')
    prepared = _native(inputs, 'councils', source, 'council_prepared',
                       dict(council_id=source['id'], session_id=source['session_id']))
    index = next(index for index, (_, old) in enumerate(inputs.history) if old is prepared)
    _require(index > 0, 'work_source_invalid')
    session = _session(inputs, source)
    authors = [inputs.assignment(key) for key in source['author_assignment_ids']]
    reviewers = [inputs.assignment(key) for key in session['participant_assignment_ids']]
    _require(len(authors) == 1 and set(source['required_roles']) == {'domain', 'methodology', 'critical'}
             and prepared['state']['review_sessions'].get(session['id']) == session
             and all(prepared['state']['assignments'].get(a['id']) == a for a in [*authors, *reviewers]),
             'work_source_invalid')
    # Replay at the immutable pre-command context: validates reference availability,
    # owner/resolver roles, distinct actors and frozen assignment/session binding.
    prior = at(inputs, index - 1)
    prepare_council(prior, dict(council=source, review_session=session, assignments=[*authors, *reviewers]))
    consumed = [session['input_binding']]
    consumed.extend(ref for ref in source['allowed_evidence_refs'] if ref not in consumed)
    if source['node'] == 'issue_scope':
        proposal = _proposal(_context(prior), session['input_binding'])
        _require(source['attempt'] == proposal['id'] and authors[0]['actor_id'] == proposal['producer_id']
                 and set(source['issue_ids']) == {r['issue_ref']['artifact_id'] for r in proposal['changes']},
                 'work_source_invalid')
        # Disagreement and historical proposal staleness do not erase real work.
        question = 'Review M1 issue scope proposal'
    elif source['node'] == 'source_analysis':
        captures = captured_records(prior)
        captured = {('m1/intake/blobs/' + row['sha256'], row['sha256']) for row in captures}
        _require(all((ref['artifact_id'], ref['sha256']) in captured for ref in consumed), 'work_source_invalid')
        question = 'Review M1 captured sources'
    else:
        _require(source['node'] == 'atlas-evidence-review', 'work_source_invalid')
        _atlas_review_input(prior, source, session, authors[0])
        question = 'Review Atlas evidence for the research question'
    submissions = _submissions(inputs, source)
    for phase, members in submissions.items():
        for submission in members.values():
            registered = _native(inputs, 'council_submissions', submission, 'council_submission_registered',
                dict(submission_id=submission['id'], session_id=session['id'], phase=phase))
            step = next(i for i, (_, old) in enumerate(inputs.history) if old is registered)
            _require(step > index, 'work_source_invalid')
            # This also rechecks phase ordering, actual author, disclosed responses
            # and evidence against the input context used by that submission.
            register_submission(at(inputs, step - 1), {'submission': submission})
    required = set(session['participant_assignment_ids'])
    _require(all(set(submissions[phase]) == required for phase in ('initial', 'response', 'final')),
             'work_source_incomplete')
    finals = {row['recommendation'] for row in submissions['final'].values()}
    status = 'awaiting_input' if 'defer' in finals else ('inconclusive' if 'revise' in finals else 'completed')
    owner = authors[0]
    envelope = {key: source[key] for key in ('schema_version', 'workflow_version', 'content_origin')}
    work = dict(**envelope, id=identity(record_id, 'work'), event_id=identity(record_id, 'event'),
        project_id=inputs.project, producer_id=owner['actor_id'], provenance_status='declared_only',
        observation_refs=[], assignment_id=owner['id'], milestone='M1', node=source['node'],
        question=question, input_refs=deepcopy(consumed), work='Independent council review',
        acceptance_rule='All required perspectives record final judgments')
    return dict(id=record_id, project_id=inputs.project, work=work,
                resource_request=dict(returns=0, verification_runs=0, estimated_cost=None, cost_status='unknown'),
                status=status, correction_ref=None)


def _source(inputs, kind, ref, record_id):
    collection = 'councils' if kind == 'council' else 'verifications'
    source = inputs.reference(ref, collection, 'Verification' if kind == 'verification' else None)
    canonical_ref = _record_ref(inputs, collection, source)
    if kind == 'council' and source.get('node') in ('issue_scope', 'source_analysis', 'atlas-evidence-review'):
        return _non_node_council(inputs, source, record_id), canonical_ref
    if kind == 'council':
        _require(_common(source, _COUNCIL_FIELDS, inputs.project), 'work_source_invalid')
        prepared = _native(inputs, 'councils', source, 'council_prepared',
                           dict(council_id=source['id'], session_id=source['session_id']))
        session = _session(inputs, source)
        artifacts = [record for record in inputs.state.get('m1_node_revisions', {}).values()
                     if record['node'] == source['node'] and record['attempt'] == source['attempt']]
        _require(len(artifacts) == 1, 'work_source_invalid')
        artifact = artifacts[0]
        _require(_shape(artifact, inputs.project), 'work_source_invalid')
        _native(inputs, 'm1_node_revisions', artifact, 'm1_node_registered',
                dict(node=artifact['node'], revision_id=artifact['id'], attempt=artifact['attempt']))
        expected_binding = dict(project_id=inputs.project, artifact_id=f"m1/nodes/{artifact['node']}",
                                sha256=store._hash(store._canonical(artifact)))
        _require(_node(session['input_binding']) == _node(expected_binding), 'work_source_invalid')
        authors = [inputs.assignment(identity) for identity in source['author_assignment_ids']]
        reviewers = [inputs.assignment(identity) for identity in session['participant_assignment_ids']]
        _require(prepared['state']['review_sessions'].get(session['id']) == session
                 and all(prepared['state']['assignments'].get(a['id']) == a for a in [*authors, *reviewers]),
                 'work_source_invalid')
        submissions = _submissions(inputs, source)
        for phase, members in submissions.items():
            for submission in members.values():
                _native(inputs, 'council_submissions', submission, 'council_submission_registered',
                        dict(submission_id=submission['id'], session_id=session['id'], phase=phase))
                actor = inputs.assignment(submission['assignment_id'])
                _require(submission['producer_id'] == actor['actor_id']
                         and submission['input_binding'] == session['input_binding'], 'work_source_invalid')
        # A native replacement may repair an incorrect declared author even
        # after B02 phases finished. This setup never represented valid M1
        # review work; authenticate its history before excluding it.
        if (source['milestone'] == 'M1' and authors
                and all(a['role'] == 'owner' and a['milestone'] == 'M1' for a in authors)
                and {a['actor_id'] for a in authors} != {artifact['producer_id']}
                and _node_identity(inputs, artifact['node'])[0]['id'] != artifact['id']):
            for successor in inputs.state['m1_node_revisions'].values():
                if successor['node'] != artifact['node'] or successor['previous_ref_key'] is None:
                    continue
                _require(_shape(successor, inputs.project), 'work_source_invalid')
                _native(inputs, 'm1_node_revisions', successor, 'm1_node_registered',
                        dict(node=successor['node'], revision_id=successor['id'], attempt=successor['attempt']))
                if _node(json.loads(successor['previous_ref_key'])) == _node(expected_binding):
                    raise ValueError('work_source_ineligible')
        required = set(session['participant_assignment_ids'])
        _require(all(set(submissions[phase]) == required for phase in ('initial', 'response', 'final')),
                 'work_source_incomplete')
        _require(_council(inputs, artifact, session['input_binding']) == source, 'work_source_invalid')
        finals = {row['recommendation'] for row in submissions['final'].values()}
        _require(finals <= {'ready', 'ready_with_limits', 'revise', 'defer'}, 'work_source_invalid')
        status = 'awaiting_input' if 'defer' in finals else ('inconclusive' if 'revise' in finals else 'completed')
        owner = inputs.assignment(source['author_assignment_ids'][0])
        node = artifact['node']; basis = artifact
        question, work, rule = f'Review M1 {node}', 'Independent council review', 'All required perspectives record final judgments'
        consumed = [session['input_binding']]
        returns, runs = int(artifact['previous_ref_key'] is not None), 0
    else:
        _native(inputs, 'verifications', source, 'verification_prepared', source)
        owner = inputs.assignment(source['owner_assignment_id'])
        _require(owner['role'] == 'owner' and source['producer_id'] == owner['actor_id'], 'work_source_invalid')
        results = []
        for event in inputs.history[-1][1]['events']:
            if event['type'] == 'verification_result_registered' and event['payload']['verification_id'] == source['id']:
                result = inputs.registered('verification_results', event['payload']['id'], 'VerificationResult')
                _native(inputs, 'verification_results', result, 'verification_result_registered', result)
                results.append(result)
        # Verified cumulative event order, never UUID-sorted state-map order.
        outcome = results[-1]['outcome'] if results else None
        status = 'pending' if outcome is None else ('completed' if outcome in ('supported', 'refuted') else outcome)
        issues = [inputs.registered('issues', issue_id, 'Issue') for issue_id in source['issue_ids']]
        _require(bool(issues) and all(issue['resolution_condition'] == source['acceptance_rule'] for issue in issues),
                 'work_source_invalid')
        node = issues[0]['origin']['node']; basis = source
        question, work, rule, consumed = source['question'], source['method'], source['acceptance_rule'], source['input_refs']
        returns, runs = 0, int(source['id'] in _counts(inputs)[1])
    _require(owner['role'] == 'owner' and bool(consumed), 'work_source_invalid')
    envelope = {key: basis[key] for key in ('schema_version', 'workflow_version', 'content_origin')}
    work = dict(**envelope, id=identity(record_id, 'work'), event_id=identity(record_id, 'event'), project_id=inputs.project,
        producer_id=owner['actor_id'], provenance_status='declared_only', observation_refs=[], assignment_id=owner['id'],
        milestone=owner['milestone'], node=node, question=question, input_refs=deepcopy(consumed), work=work, acceptance_rule=rule)
    record = dict(id=record_id, project_id=inputs.project, work=work,
        resource_request=dict(returns=returns, verification_runs=runs, estimated_cost=None, cost_status='unknown'),
        status=status, correction_ref=None)
    return record, canonical_ref


def _record_sources(inputs):
    recorded = {}
    for record_id in inputs.state.get('work_records', {}):
        record = inputs.registered('work_records', record_id)
        first_index = next(index for index, (_, old) in enumerate(inputs.history)
                           if record_id in old['state'].get('work_records', {}))
        event = inputs.history[first_index][1]['events'][-1]
        payload = {key: value for key, value in event['payload'].items() if key != '_command_request'}
        _require(event['type'] == 'native_work_recorded'
                 and _valid(dict(record_id='uuid', source_kind=('enum', ('council', 'verification')),
                                 source_ref=dict(project_id='uuid', head_id='sha256', artifact_id='text', sha256='sha256')), payload)
                 and payload['record_id'] == record_id, 'work_source_invalid')
        historical = _context(at(inputs, first_index))
        expected, ref = _source(historical, payload['source_kind'], payload['source_ref'], record_id)
        _require(expected == record and payload['source_ref'] == ref, 'work_source_invalid')
        key = (payload['source_kind'], _node(ref))
        _require(key not in recorded, 'work_source_already_recorded')
        recorded[key] = record_id
    return recorded


def work_sources(snapshot: dict) -> list[dict]:
    """List actual completed councils and prepared checks, never invented work."""
    inputs = _context(snapshot); recorded = _record_sources(inputs); sources = []
    for kind, collection in (('council', 'councils'), ('verification', 'verifications')):
        for source in inputs.state.get(collection, {}).values():
            ref = _record_ref(inputs, collection, source)
            try:
                _source(inputs, kind, ref, identity(source['id'], 'work-preview'))
            except ValueError as error:
                if str(error) in ('work_source_incomplete', 'work_source_ineligible'):
                    continue
                raise
            sources.append(dict(source_kind=kind, source_ref=ref, recorded=(kind, _node(ref)) in recorded))
    return sources


def record_work(snapshot: dict, payload: dict) -> dict:
    from .contracts import _REF
    _require(_valid(dict(record_id='uuid', source_kind=('enum', ('council', 'verification')), source_ref=_REF), payload),
             'work_payload_invalid')
    inputs = _context(snapshot); _fresh_ids(inputs, [payload['record_id']])
    record, source_ref = _source(inputs, payload['source_kind'], payload['source_ref'], payload['record_id'])
    _require((payload['source_kind'], _node(source_ref)) not in _record_sources(inputs), 'work_source_already_recorded')
    return dict(state_patch={'work_records': {**inputs.state.get('work_records', {}), record['id']: record}},
        event={**store._VERSION, 'type': 'native_work_recorded', 'payload': dict(record_id=record['id'],
            source_kind=payload['source_kind'], source_ref=source_ref)}, object_inputs={record['id']: store._canonical(record)})


def refresh_ledger(snapshot: dict, payload: dict) -> dict:
    _require(_valid({'ledger_id': 'uuid'}, payload), 'work_payload_invalid')
    inputs = _context(snapshot); _fresh_ids(inputs, [payload['ledger_id']])
    _require(all(source['recorded'] for source in work_sources(snapshot)), 'work_record_required')
    records = inputs.state.get('work_records', {})
    ledger = dict(id=payload['ledger_id'], project_id=inputs.project,
                  work_refs=[_record_ref(inputs, 'work_records', records[key]) for key in sorted(records)])
    returns, begun = _counts(inputs)
    return dict(state_patch=dict(work_ledgers={**inputs.state.get('work_ledgers', {}), ledger['id']: ledger},
        work_ledger_id=ledger['id'], returns_used=returns, verification_runs_used=len(begun), observed_cost=None, cost_status='unknown'),
        event={**store._VERSION, 'type': 'native_work_ledger_refreshed', 'payload': {'ledger_id': ledger['id']}},
        object_inputs={ledger['id']: store._canonical(ledger)})


def accounting_status(snapshot: dict) -> dict:
    inputs = _context(snapshot)
    reasons = []
    try:
        mode = return_mode(inputs.state)
    except ValueError:
        mode = None
        reasons.append('return_policy_invalid')
    if any(not source['recorded'] for source in work_sources(snapshot)):
        reasons.append('work_record_required')
    try:
        _ledger(inputs, _References(inputs))
        ledger = inputs.registered('work_ledgers', inputs.state.get('work_ledger_id'))
        _native(inputs, 'work_ledgers', ledger, 'native_work_ledger_refreshed', {'ledger_id': ledger['id']})
    except ValueError:
        reasons.append('work_ledger_refresh_required')
    returns, begun = _counts(inputs)
    if inputs.state.get('returns_used') != returns or inputs.state.get('verification_runs_used') != len(begun):
        reasons.append('work_ledger_refresh_required')
    if inputs.state.get('observed_cost') is not None or inputs.state.get('cost_status') != 'unknown':
        reasons.append('work_cost_unknown')
    for used, maximum, reason in ((returns, 'max_returns', 'returns_exhausted'),
                                  (len(begun), 'max_verification_runs', 'verification_runs_exhausted')):
        if type(inputs.state.get(maximum)) is not int or inputs.state[maximum] < 0:
            reasons.append('budget_invalid')
        elif used > inputs.state[maximum] and not (maximum == 'max_returns' and mode == 'evidence_driven'):
            reasons.append(reason)
    return dict(ready=not reasons, reason_codes=list(dict.fromkeys(reasons)),
                return_policy=dict(mode=mode, returns_used=returns,
                                   count_limit=None if mode == 'evidence_driven' else inputs.state.get('max_returns')),
                required_actions=[f'Complete {reason} using explicit work record/ledger commands.' for reason in dict.fromkeys(reasons)])
