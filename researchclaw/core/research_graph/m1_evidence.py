"""Supplied source captures and independent, native A05 source checks.

Recorded access/origins are declarations. Literal comparisons inspect supplied
UTF-8 bytes; they do not authenticate sources or execute scientific experiments.
"""
from copy import deepcopy
from datetime import datetime
from uuid import UUID, uuid5

from . import store
from .contracts import _COMMON
from .councils import _common, _fresh_ids, _record_ref, _valid
from .dependencies import _node
from .evidence_origins import group_origins
from .gates import _status
from .issues import _require
from .m1_nodes import _context, _native, _node_identity, current_node
from .m1_search import corpus_status, current_corpus

_REF = {'project_id': 'uuid', 'head_id': 'sha256', 'artifact_id': 'text', 'sha256': 'sha256'}
_ACCESS = ('unavailable', 'metadata_only', 'abstract', 'full_text')
_TEXTS = ('array', 'text')
_SOURCE = dict(source_id='text', access_status=('enum', _ACCESS), access_url=('nullable', 'text'),
    accessed_at='text', raw_text=('nullable', 'text'), origin_group_id='text',
    origin_description=('nullable', 'text'), limitations=_TEXTS)
_CLAIM = dict(claim_id='text', source_id='text', source_ref=_REF, locator='text', span_start='text',
    span_end='text', extracted_text='text', access_level=('enum', _ACCESS), interpretation='text', limitations=_TEXTS)
_COMPARE = dict(item_id='text', source_ref=_REF, locator='text', span_start='text', span_end='text',
    access_level=('enum', _ACCESS), observed_text='text', interpretation='text')
_OBS_FIELDS = set(_COMMON) | {'verification_ref', 'node_ref', 'checker_assignment_id', 'comparisons', 'limitations'}
_RECHECK_ACTION = ('For a prior unresolved planned check, explicitly return checking to open, prepare a new A05 '
                  'Verification against repaired current inputs with the original resolution condition, begin checking, '
                  'register the actual replacement comparison result, and obtain an independent A04 resolution.')
_SETUP_FIELDS = set(_COMMON) | {'node_ref', 'checker_assignment_id', 'resolver_assignment_id', 'budget_alias', 'budget_sha256'}


def _id(record, suffix):
    return str(uuid5(UUID(record['id']), suffix))


def _envelope(record, suffix, actor=None):
    return {**{key: record[key] for key in _COMMON}, 'id': _id(record, suffix),
            'event_id': _id(record, suffix + '/event'), 'producer_id': actor or record['producer_id'],
            'provenance_status': 'declared_only', 'observation_refs': []}


def _alias(kind, identity):
    return f'm1/{kind}/{store._hash(identity.encode())}'


def _spans(shape, rows):
    if type(rows) is not list:
        return False
    for row in rows:
        if (type(row) is not dict or any(type(row.get(k)) is not int for k in ('span_start', 'span_end'))
                or not 0 <= row['span_start'] < row['span_end']):
            return False
        if not _valid(shape, {**row, 'span_start': str(row['span_start']), 'span_end': str(row['span_end'])}):
            return False
    return True


def content_shape(node, content):
    if node == 'collect':
        return _valid({'sources': ('array', _SOURCE), 'limitations': _TEXTS}, content)
    return (type(content) is dict and set(content) == {'claims', 'limitations'}
            and _spans(_CLAIM, content['claims'])
            and _valid(('array', {'source_id': 'text', 'reason': 'text'}), content['limitations']))


def _objects(artifact):
    objects = {}
    if artifact['node'] == 'collect':
        for source in artifact['content']['sources']:
            metadata = {key: value for key, value in source.items() if key != 'raw_text'}
            metadata['raw_text_sha256'] = store._hash(source['raw_text'].encode()) if source['raw_text'] is not None else None
            objects[_alias('sources', source['source_id'])] = store._canonical(metadata)
            if source['raw_text'] is not None:
                objects[_alias('source-text', source['source_id'])] = source['raw_text'].encode()
            origin = dict(origin_group_id=source['origin_group_id'], description=source['origin_description'])
            objects[_alias('origins', source['origin_group_id'])] = store._canonical(origin)
    else:
        for claim in artifact['content']['claims']:
            objects[_alias('claims', claim['claim_id'])] = store._canonical(claim)
    return objects


def _object_ref(inputs, artifact, alias):
    data = _objects(artifact)[alias]
    head = _record_ref(inputs, 'm1_node_revisions', artifact)['head_id']
    ref = dict(project_id=inputs.project, head_id=head, artifact_id=alias, sha256=store._hash(data))
    inputs.reference(ref)
    return ref


def _sources(inputs, collect):
    return {row['source_id']: dict(metadata_ref=_object_ref(inputs, collect, _alias('sources', row['source_id'])),
        raw_ref=_object_ref(inputs, collect, _alias('source-text', row['source_id'])) if row['raw_text'] is not None else None,
        access_status=row['access_status']) for row in collect['content']['sources']}


def validate_content(snapshot, inputs, artifact):
    corpus = current_corpus(snapshot)
    kept = {row['source_id']: row for row in corpus['kept_sources']}
    _require(_node(artifact['input_refs']['screen']) == _node(corpus['corpus_ref']), 'm1_evidence_source_invalid')
    if artifact['node'] == 'collect':
        rows = artifact['content']['sources']
        _require(len(rows) == len(kept) and {row['source_id'] for row in rows} == set(kept), 'm1_evidence_coverage_invalid')
        origins = {}
        for row in rows:
            _require(_ACCESS.index(row['access_status']) <= _ACCESS.index(kept[row['source_id']]['access_status']),
                     'm1_evidence_access_invalid')
            try:
                datetime.fromisoformat(row['accessed_at'].replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('m1_evidence_source_invalid') from None
            _require((row['raw_text'] is None) == (row['access_status'] == 'unavailable'), 'm1_evidence_access_invalid')
            _require(row['access_status'] == 'full_text' or bool(row['limitations']), 'm1_evidence_limitation_required')
            _require((row['origin_group_id'] == 'unknown' and row['origin_description'] is None)
                     or (row['origin_group_id'] != 'unknown' and _valid('text', row['origin_description'])),
                     'm1_evidence_origin_invalid')
            _require(row['origin_group_id'] not in origins or origins[row['origin_group_id']] == row['origin_description'],
                     'm1_evidence_origin_invalid')
            origins[row['origin_group_id']] = row['origin_description']
    else:
        _require(corpus_status(snapshot)['approved'], 'm1_corpus_approval_required')
        collect, _ = current_node(inputs, 'collect')
        refs = _sources(inputs, collect)
        claims = artifact['content']['claims']
        _require(len({row['claim_id'] for row in claims}) == len(claims), 'm1_evidence_source_invalid')
        for row in claims:
            _require(row['source_id'] in refs and refs[row['source_id']]['raw_ref'] is not None
                     and row['source_ref'] == refs[row['source_id']]['raw_ref'], 'm1_evidence_source_invalid')
            _require(row['access_level'] == refs[row['source_id']]['access_status'], 'm1_evidence_access_invalid')
            _require(row['span_end'] <= len(inputs.reference(row['source_ref']).decode()), 'm1_evidence_source_invalid')
            _require(row['access_level'] == 'full_text' or bool(row['limitations']), 'm1_evidence_limitation_required')
        limited = artifact['content']['limitations']
        _require(all(row['source_id'] in kept for row in limited)
                 and {row['source_id'] for row in claims + limited} == set(kept), 'm1_evidence_coverage_invalid')
    return _objects(artifact)


def _setup(inputs, artifact, ref):
    matches = []
    for identity in inputs.state.get('m1_evidence_setups', {}):
        record = inputs.registered('m1_evidence_setups', identity)
        _require(_common(record, _SETUP_FIELDS, inputs.project), 'm1_evidence_setup_invalid')
        if record['node_ref'] == ref:
            native = _native(inputs, 'm1_evidence_setups', record, 'm1_evidence_assigned',
                             {'setup_id': identity, 'node_ref': ref})
            checker = inputs.assignment(record['checker_assignment_id'])
            resolver = inputs.assignment(record['resolver_assignment_id'])
            _require(checker['role'] == 'owner' and resolver['role'] == 'resolver'
                     and checker['milestone'] == resolver['milestone'] == 'M1'
                     and len({checker['actor_id'], resolver['actor_id'], artifact['producer_id']}) == 3
                     and all(native['state']['assignments'][a['id']] == a for a in (checker, resolver)),
                     'm1_evidence_actor_invalid')
            matches.append(record)
    _require(len(matches) <= 1, 'm1_evidence_setup_invalid')
    return matches[0] if matches else None


def assign_evidence(snapshot, payload):
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'setup_id', 'node_ref', 'checker_assignment', 'resolver_assignment'},
             'm1_evidence_setup_invalid')
    _require(_valid('uuid', payload['setup_id']), 'm1_evidence_setup_invalid')
    node = payload['node_ref'].get('artifact_id', '').removeprefix('m1/nodes/') if type(payload['node_ref']) is dict else None
    _require(node in ('collect', 'extract'), 'm1_evidence_setup_invalid')
    artifact, ref = current_node(inputs, node)
    _require(payload['node_ref'] == ref and _setup(inputs, artifact, ref) is None, 'm1_evidence_setup_invalid')
    assignments = [payload['checker_assignment'], payload['resolver_assignment']]
    for a, role in zip(assignments, ('owner', 'resolver')):
        _require(_valid(dict(id='uuid', project_id='uuid', actor_id='text', role=('enum', (role,)),
                            milestone=('enum', ('M1',)), active='bool'), a)
                 and a['project_id'] == inputs.project and a['active'] is True, 'm1_evidence_actor_invalid')
    _require(len({artifact['producer_id'], *(a['actor_id'] for a in assignments)}) == 3, 'm1_evidence_actor_invalid')
    _fresh_ids(inputs, [payload['setup_id'], *(a['id'] for a in assignments)])
    budget = {**store._VERSION, 'project_id': inputs.project, **{key: inputs.state[key] for key in
        ('max_returns', 'returns_used', 'max_verification_runs', 'verification_runs_used',
         'execution_cost_limit', 'observed_cost', 'cost_status')}}
    alias = f"m1/evidence-budgets/{payload['setup_id']}"
    setup = {**_envelope(artifact, 'setup'), 'id': payload['setup_id'], 'node_ref': ref,
             'checker_assignment_id': assignments[0]['id'], 'resolver_assignment_id': assignments[1]['id'],
             'budget_alias': alias, 'budget_sha256': store._hash(store._canonical(budget))}
    patch = dict(assignments={**inputs.state.get('assignments', {}), **{a['id']: a for a in assignments}},
                 m1_evidence_setups={**inputs.state.get('m1_evidence_setups', {}), setup['id']: setup})
    objects = {alias: store._canonical(budget), setup['id']: store._canonical(setup),
               **{a['id']: store._canonical(a) for a in assignments}}
    if node == 'collect':
        sources, dependencies = {}, dict(inputs.state.get('dependencies', {}))
        for row in artifact['content']['sources']:
            metadata = _object_ref(inputs, artifact, _alias('sources', row['source_id']))
            source = {**_envelope(artifact, 'source/' + row['source_id']), 'source_ref': metadata}
            dependency = {**_envelope(artifact, 'dependency/' + row['source_id']),
                'from_ref': _object_ref(inputs, artifact, _alias('origins', row['origin_group_id'])),
                'to_ref': metadata, 'relation': 'derived_from', 'origin_group_id': row['origin_group_id']}
            sources[source['id']] = source
            dependencies[dependency['id']] = dependency
            objects.update({r['id']: store._canonical(r) for r in (source, dependency)})
        patch.update(evidence_sources=sources, dependencies=dependencies)
    return dict(state_patch=patch, object_inputs=objects,
                event={**store._VERSION, 'type': 'm1_evidence_assigned', 'payload': {'setup_id': setup['id'], 'node_ref': ref}})


def _issue(artifact, ref, checker, suffix, question, rule):
    return {**_envelope(artifact, suffix, checker['actor_id']),
        'origin': dict(milestone='M1', node=artifact['node'], attempt=artifact['attempt'], local_issue_id=suffix),
        'question': question, 'category': 'source', 'target_refs': [ref], 'severity': 'major',
        'blocking_scope': [dict(kind='node', milestone='M1', target_id=artifact['node'])],
        'resolution_condition': rule, 'owner_assignment_id': checker['id']}


def _mismatch_issue(artifact, ref, checker, claim_id):
    return _issue(artifact, ref, checker, 'source-mismatch/' + claim_id,
        'How should the extracted claim be repaired to match the supplied source span?',
        'Independent source verification confirms the repaired claim matches its supplied source span.')


def _event(issue, checker, status, previous=None, refs=()):
    return {**_envelope(issue, 'transition/' + status, checker['actor_id']), 'issue_id': issue['id'],
            'from_status': previous, 'to_status': status, 'actor_assignment_id': checker['id'],
            'rationale': 'Register the explicit planned source check' if previous is None else 'Begin the fixed source check',
            'verification_refs': list(refs), 'successor_ids': []}


def _planned(inputs, artifact, ref, setup):
    checker = inputs.assignment(setup['checker_assignment_id'])
    rule = 'Independent literal source comparisons cover available items, preserve access limitations, and find no extraction mismatch.'
    question = 'Do the supplied captures and extracted spans satisfy the fixed source-check criterion?'
    issue = _issue(artifact, ref, checker, 'planned-source-check', question, rule)
    budget_ref = {**_record_ref(inputs, 'm1_evidence_setups', setup), 'artifact_id': setup['budget_alias'], 'sha256': setup['budget_sha256']}
    inputs.reference(budget_ref)
    verification = {**_envelope(artifact, 'source-verification', checker['actor_id']), 'issue_ids': [issue['id']],
        'method': 'source_check', 'question': question, 'input_refs': [ref, *artifact['input_refs'].values()],
        'acceptance_rule': rule, 'owner_assignment_id': checker['id'], 'budget_ref': budget_ref}
    return checker, issue, verification


def _comparisons(inputs, artifact, observation):
    _require(_common(observation, _OBS_FIELDS, inputs.project)
             and _valid(_REF, observation['node_ref']) and _valid(_REF, observation['verification_ref'])
             and _valid('uuid', observation['checker_assignment_id']) and _valid(_TEXTS, observation['limitations'])
             and _spans(_COMPARE, observation['comparisons']), 'm1_evidence_observation_invalid')
    collect = artifact if artifact['node'] == 'collect' else current_node(inputs, 'collect')[0]
    refs = _sources(inputs, collect)
    if artifact['node'] == 'collect':
        expected = {row['source_id']: {**row, 'source_ref': refs[row['source_id']]['raw_ref']}
                    for row in collect['content']['sources'] if row['raw_text'] is not None}
    else:
        expected = {row['claim_id']: row for row in artifact['content']['claims']}
    mismatches = []
    for row in observation['comparisons']:
        _require(row['item_id'] in expected, 'm1_evidence_coverage_invalid')
        item = expected[row['item_id']]
        access = item['access_status'] if artifact['node'] == 'collect' else item['access_level']
        _require(row['access_level'] == access, 'm1_evidence_access_invalid')
        _require(row['source_ref'] == item['source_ref'], 'm1_evidence_source_invalid')
        raw = inputs.reference(row['source_ref']).decode()
        _require(row['span_end'] <= len(raw) and row['observed_text'] == raw[row['span_start']:row['span_end']],
                 'm1_evidence_observation_invalid')
        if artifact['node'] == 'extract':
            _require(all(row[key] == item[key] for key in ('locator', 'span_start', 'span_end')), 'm1_evidence_source_invalid')
            if row['observed_text'] != item['extracted_text']:
                mismatches.append(row['item_id'])
    _require(len(observation['comparisons']) == len(expected)
             and {row['item_id'] for row in observation['comparisons']} == set(expected), 'm1_evidence_coverage_invalid')
    for source in observation['observation_refs']:
        inputs.reference(source)
    return mismatches


def _observations(inputs, artifact, ref, setup, verification_ref):
    found = []
    for identity in inputs.state.get('m1_source_observations', {}):
        record = inputs.registered('m1_source_observations', identity)
        if record.get('node_ref') != ref:
            continue
        _native(inputs, 'm1_source_observations', record, 'm1_source_observed', record)
        _require(record['verification_ref'] == verification_ref
                 and record['checker_assignment_id'] == setup['checker_assignment_id']
                 and record['producer_id'] == inputs.assignment(setup['checker_assignment_id'])['actor_id'],
                 'm1_evidence_actor_invalid')
        found.append((record, _comparisons(inputs, artifact, record)))
    return found


def observe_evidence(snapshot, payload):
    inputs = _context(snapshot)
    _require(type(payload) is dict and set(payload) == {'observation'} and type(payload['observation']) is dict,
             'm1_evidence_observation_invalid')
    observation = deepcopy(payload['observation'])
    ref = observation.get('node_ref')
    _require(_valid(_REF, ref), 'm1_evidence_observation_invalid')
    node = ref.get('artifact_id', '').removeprefix('m1/nodes/')
    _require(node in ('collect', 'extract'), 'm1_evidence_observation_invalid')
    artifact, current = current_node(inputs, node)
    setup = _setup(inputs, artifact, current)
    _require(setup is not None and ref == current, 'm1_evidence_setup_invalid')
    checker, issue, verification = _planned(inputs, artifact, current, setup)
    _require(observation.get('checker_assignment_id') == checker['id'] and observation.get('producer_id') == checker['actor_id'],
             'm1_evidence_actor_invalid')
    actual = inputs.verification(verification['id'], issue['id'])
    _require(actual == verification, 'm1_evidence_verification_invalid')
    _native(inputs, 'verifications', actual, 'verification_prepared', actual)
    _require(observation.get('verification_ref') == _record_ref(inputs, 'verifications', actual), 'm1_evidence_verification_invalid')
    _require(_status(inputs, inputs.registered('issues', issue['id'], 'Issue'))[0] == 'checking', 'm1_evidence_checking_required')
    _comparisons(inputs, artifact, observation)
    _fresh_ids(inputs, [observation['id']])
    return dict(state_patch={'m1_source_observations': {**inputs.state.get('m1_source_observations', {}), observation['id']: observation}},
        object_inputs={observation['id']: store._canonical(observation)},
        event={**store._VERSION, 'type': 'm1_source_observed', 'payload': observation})


def prepare_evidence_check(snapshot: dict, *, node_id: str) -> dict:
    inputs = _context(snapshot)
    _require(node_id in ('collect', 'extract'), 'm1_node_invalid')
    artifact, ref = current_node(inputs, node_id)
    reasons, plans, mismatch_plans = [], [], []
    setup = _setup(inputs, artifact, ref)
    issue_id, verification_ref = None, None
    from .m1_nodes import review_node
    for parent in artifact['input_refs']:
        if not review_node(snapshot, parent)['ready']:
            reasons.append('upstream_review_required')
    if node_id == 'extract' and not corpus_status(snapshot)['approved']:
        reasons.append('corpus_approval_required')
    collect = artifact if node_id == 'collect' else current_node(inputs, 'collect')[0]
    if any(row['access_status'] == 'unavailable' for row in collect['content']['sources']):
        reasons.append('source_unavailable')
    if node_id == 'extract' and artifact['content']['limitations']:
        reasons.append('source_extraction_gap')
    if setup is None:
        reasons.append('source_check_assignment_required')
    else:
        checker, issue, verification = _planned(inputs, artifact, ref, setup)
        issue_id = issue['id']
        status, latest = None, None
        if issue_id not in inputs.state.get('issues', {}):
            plans.append(dict(operation='issue.event', payload={'issue': issue, 'event': _event(issue, checker, 'open')}))
            reasons.append('source_check_issue_required')
        else:
            _require(inputs.registered('issues', issue_id, 'Issue') == issue, 'm1_evidence_verification_invalid')
            status, latest = _status(inputs, issue)
            if verification['id'] not in inputs.state.get('verifications', {}):
                plans.append(dict(operation='verification.prepare', payload={'verification': verification}))
                reasons.append('source_verification_required')
            else:
                actual = inputs.verification(verification['id'], issue_id)
                _require(actual == verification, 'm1_evidence_verification_invalid')
                _native(inputs, 'verifications', actual, 'verification_prepared', actual)
                verification_ref = _record_ref(inputs, 'verifications', actual)
                if status in ('open', 'reopened', 'deferred', 'transferred'):
                    event = _event(issue, checker, 'checking', status, [verification_ref])
                    event.update(_envelope(issue, 'checking/' + latest['id'], checker['actor_id']))
                    plans.append(dict(operation='issue.event', payload={'issue': None, 'event': event}))
                observations = _observations(inputs, artifact, ref, setup, verification_ref)
                observation_refs = {_node(_record_ref(inputs, 'm1_source_observations', row)): row for row, _ in observations}
                for observation, mismatches in observations:
                    for claim_id in mismatches:
                        reasons.append('source_mismatch')
                        proposal = _mismatch_issue(artifact, ref, checker, claim_id)
                        if inputs.state.get('issues', {}).get(proposal['id']) != proposal:
                            mismatch_plans.append(dict(operation='issue.event', payload={'issue': proposal, 'event': _event(proposal, checker, 'open')}))
                results = []
                for identity in inputs.state.get('verification_results', {}):
                    result = inputs.registered('verification_results', identity, 'VerificationResult')
                    if result['verification_id'] == verification['id']:
                        _native(inputs, 'verification_results', result, 'verification_result_registered', result)
                        results.append(result)
                linked = []
                if status == 'resolved':
                    resolver = inputs.assignment(latest['actor_assignment_id'])
                    _require(resolver['id'] == setup['resolver_assignment_id'] and resolver['actor_id'] != checker['actor_id'],
                             'm1_evidence_actor_invalid')
                    linked = [inputs.reference(r, 'verification_results', 'VerificationResult') for r in latest['verification_refs']]
                    linked = [r for r in linked if r in results]
                order = {head: index for index, (head, _) in enumerate(inputs.history)}
                results.sort(key=lambda result: order[_record_ref(inputs, 'verification_results', result)['head_id']])
                chosen = linked or results[-1:]
                if not chosen:
                    reasons.append('source_check_result_required')
                valid_output = False
                for result in chosen:
                    _require(result['producer_id'] == checker['actor_id'], 'm1_evidence_actor_invalid')
                    for output in result['output_refs']:
                        inputs.reference(output)
                        if _node(output) in observation_refs:
                            valid_output = True
                    if result['outcome'] != 'supported':
                        reasons.append('source_check_' + result['outcome'])
                    elif verification['acceptance_rule'] not in result['checked_scope']:
                        reasons.append('source_check_scope_missing')
                if not valid_output:
                    reasons.append('source_observation_required')
                if status != 'resolved' or not linked:
                    reasons.append('source_check_resolution_required')
    for identity in inputs.state.get('issues', {}):
        if identity == issue_id:
            continue
        issue = inputs.registered('issues', identity, 'Issue')
        if (dict(kind='node', milestone='M1', target_id=node_id) in issue['blocking_scope']
                and issue['severity'] != 'optional' and _status(inputs, issue)[0] != 'resolved'):
            reasons.append('blocking_issue_unresolved')
    reasons = list(dict.fromkeys(reasons))
    return deepcopy(dict(ready=not reasons, reason_codes=reasons,
        required_actions=[f'Address {reason} before advancing this node.' for reason in reasons]
            + ([_RECHECK_ACTION] if 'blocking_issue_unresolved' in reasons else []),
        node_ref=ref, check_issue_id=issue_id, verification_ref=verification_ref,
        command_plans=plans, mismatch_issue_plans=mismatch_plans))


def require_mismatch_publication(snapshot, node):
    # Historical obligations survive repairs without requiring obsolete inputs
    # or a successful prior check. Native observations already froze comparisons.
    if node != 'extract':
        return
    inputs = _context(snapshot)
    artifact, ref = _node_identity(inputs, node)
    claims = {row['claim_id']: row for row in artifact['content']['claims']}
    for identity in inputs.state.get('m1_source_observations', {}):
        observation = inputs.registered('m1_source_observations', identity)
        if observation.get('node_ref') != ref:
            continue
        _native(inputs, 'm1_source_observations', observation, 'm1_source_observed', observation)
        for comparison in observation['comparisons']:
            claim = claims[comparison['item_id']]
            if comparison['observed_text'] == claim['extracted_text']:
                continue
            identity = _id(artifact, 'source-mismatch/' + comparison['item_id'])
            _require(identity in inputs.state.get('issues', {}), 'm1_issue_publication_required')
            issue = inputs.registered('issues', identity, 'Issue')
            checker = inputs.assignment(observation['checker_assignment_id'])
            _require(issue == _mismatch_issue(artifact, ref, checker, comparison['item_id']),
                     'm1_issue_publication_required')
            _status(inputs, issue)


def current_evidence(snapshot: dict) -> dict:
    inputs = _context(snapshot)
    corpus = corpus_status(snapshot)
    reasons = list(corpus['reason_codes'])
    result = dict(corpus_ref=corpus['corpus_ref'], collect_ref=None, extract_ref=None,
        kept_source_ids=sorted(row['source_id'] for row in corpus['kept_sources']),
        collected_source_refs={}, extraction_refs={}, source_groups=None, limitations=[])
    for node in ('collect', 'extract'):
        if node not in inputs.state.get('m1_node_heads', {}):
            reasons.append(node + '_required')
            continue
        try:
            artifact, ref = current_node(inputs, node)
        except ValueError as error:
            if str(error) != 'issue_reference_stale':
                raise
            reasons.append(node + '_stale')
            continue
        _require(_node(artifact['input_refs']['screen']) == _node(corpus['corpus_ref']), 'm1_evidence_source_invalid')
        result[node + '_ref'] = ref
        reasons.extend(prepare_evidence_check(snapshot, node_id=node)['reason_codes'])
        if node == 'collect':
            result['collected_source_refs'] = _sources(inputs, artifact)
            for row in artifact['content']['sources']:
                result['limitations'].extend(f"{row['source_id']}: {text}" for text in row['limitations'])
            result['limitations'].extend(artifact['content']['limitations'])
        else:
            result['extraction_refs'] = {row['claim_id']: _object_ref(inputs, artifact, _alias('claims', row['claim_id']))
                                         for row in artifact['content']['claims']}
            for row in artifact['content']['claims']:
                result['limitations'].extend(f"{row['source_id']}: {text}" for text in row['limitations'])
            result['limitations'].extend(f"{row['source_id']}: {row['reason']}" for row in artifact['content']['limitations'])
    if 'evidence_sources' not in inputs.state:
        reasons.append('evidence_sources_required')
    else:
        selected = {_node(row['source_ref']) for row in inputs.state['evidence_sources'].values()}
        expected = {_node(row['metadata_ref']) for row in result['collected_source_refs'].values()}
        if selected != expected:
            reasons.append('evidence_sources_stale')
        else:
            result['source_groups'] = group_origins(snapshot)
    reasons = list(dict.fromkeys(reasons))
    return deepcopy(dict(ready=not reasons, reason_codes=reasons,
        required_actions=[f'Address {reason} before evidence synthesis.' for reason in reasons]
            + ([_RECHECK_ACTION] if 'blocking_issue_unresolved' in reasons else []), **result))
