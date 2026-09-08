"""Read-only registered M1 views, pinned to one verified reachable commit.

The demo and live view share the core collections checked by validate_view.
Only state.artifacts supply raw-object permissions. Hypothesis display records
are per-source JSON projections, never registered objects. Content is a bounded
UTF-8 preview (content_truncated/content_length); no scientific summary is made.
Council disclosure uses only frozen public arrays, never command events,
receipts, private maps or replaced reviewers' initial bodies. Registration is
integrity-checked ancestry, not authentication of declared host provenance.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import quote

from . import store
from .budgets import budget_status
from .contracts import describe_graph
from .issues import build_issue_threads
from .roles import describe_roles

PREVIEW_CHARACTERS = 4000
_COLLECTIONS = ('nodes', 'edges', 'attempts', 'artifacts', 'sessions', 'issues',
                'responses', 'decisions', 'approvals', 'next_actions')
_SESSION_FIELDS = ('id', 'source_attempt_id', 'review_attempt_id', 'input_binding',
                   'input_refs', 'approval_id', 'hypothesis_refs', 'author_assignment_ids',
                   'author_host_task_ids', 'status', 'content_origin', 'decision_id')


def validate_view(view: dict) -> None:
    """Check the shared extensible demo/registered core without erasing origin."""
    if (type(view) is not dict or type(view.get('schema_version')) is not int
            or view['schema_version'] != 1 or view.get('workflow_version') != 'm1-graph-v1'
            or view.get('data_origin') not in ('demo', 'registered')
            or type(view.get('project')) is not dict
            or not isinstance(view['project'].get('id'), str)
            or not isinstance(view['project'].get('title'), str)
            or any(type(view.get(key)) is not list or any(type(v) is not dict for v in view[key])
                   for key in _COLLECTIONS)):
        raise ValueError('m1_view_invalid')
    for key in ('nodes', 'attempts', 'artifacts', 'sessions', 'issues', 'responses', 'decisions'):
        ids = [v.get('id') for v in view[key]]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('m1_view_invalid')
    nodes = {node['id'] for node in view['nodes']}
    if any(edge.get('from') not in nodes or edge.get('to') not in nodes for edge in view['edges']):
        raise ValueError('m1_view_invalid')


def find_decision(view: dict, decision_id: str) -> dict | None:
    return next((d for d in view['decisions'] if d['id'] == decision_id), None)


def _qualified(session_id: str, kind: str, record_id: str) -> str:
    return f'{quote(session_id, safe="")}/{kind}/{quote(record_id, safe="")}'


def _scoped(value, session_id: str):
    """Rewrite semantic issue/response identities, retaining original IDs."""
    if type(value) is list:
        return [_scoped(item, session_id) for item in value]
    if type(value) is not dict:
        return value
    result = {key: _scoped(item, session_id) for key, item in value.items()
              if key != 'submission_sha256'}
    kind = 'issue' if 'question' in value and 'raised_by' in value else (
        'response' if 'issue_id' in value and 'stance' in value else None)
    if kind and 'id' in value:
        result.update(id=_qualified(session_id, kind, value['id']),
                      original_id=value['id'], session_id=session_id)
    for key in ('issue_ids', 'related_issue_ids', 'open_blockers'):
        if key in result:
            result[key] = [_qualified(session_id, 'issue', item) for item in value[key]]
    if 'issue_id' in result:
        result['issue_id'] = _qualified(session_id, 'issue', value['issue_id'])
    if 'response_ids' in result:
        result['response_ids'] = [_qualified(session_id, 'response', item) for item in value['response_ids']]
    return result


def _session_view(session: dict) -> dict:
    result = {key: deepcopy(session[key]) for key in _SESSION_FIELDS if key in session}
    result.update(node_id='review', provenance_status=session.get('provenance_status', 'declared_only'),
                  registration_status='committed', host_provenance_status='not_observed')
    initials = session.get('initials', {})
    result['assignments'] = [{**deepcopy(a), 'initial_status': (
        'submitted' if a['id'] in initials else 'failed' if a.get('status', '').startswith('failed') else 'waiting')}
        for a in session['assignments']]
    result['assignment_history'] = [{key: deepcopy(value) for key, value in entry.items()
                                     if key != 'initial'} for entry in session.get('assignment_history', [])]
    # Replaced initials never enter disclosure. Failed sessions with incomplete
    # roles are private too; phase status alone is not sufficient authorization.
    complete = len(session['assignments']) == 3 and all(a['id'] in initials for a in session['assignments'])
    for key in ('disclosed_initials', 'disclosed_responses', 'disclosed_final_positions'):
        result[key] = _scoped(session.get(key, []), session['id']) if complete else []
    return result


def _resume(head: dict, contents: dict) -> dict:
    """Compute gates from selected state and cached exact bodies only."""
    from .approvals import CORPUS_PATHS, _current_approval
    from .literature import validate_literature
    from .packets import PACKET_VERSION, _binding, _current_attempt, _inputs, _packet

    state = head['state']
    node = state['current_node_id']
    attempt = _current_attempt(state)
    status = attempt['status'] if attempt else 'ready'
    action, reasons = 'prepare_node', []
    latest = {r['logical_path']: r for r in state.get('artifacts', [])}

    def corpus_approval():
        if any(path not in latest for path in CORPUS_PATHS):
            raise ValueError('m1_corpus_inputs_missing')
        refs = sorted((latest[path] for path in CORPUS_PATHS), key=lambda r: (r['id'], r['sha256']))
        files = {ref['logical_path']: contents[ref['sha256']] for ref in refs}
        if any(validate_literature(stage, files, files) for stage in ('search', 'collect', 'screen')):
            raise ValueError('m1_corpus_invalid')
        binding = store._hash(store._canonical({**store._VERSION, 'project_id': state['project_id'],
            'objects': [{'id': r['id'], 'sha256': r['sha256']} for r in refs]}))
        approval = _current_approval(state, {'corpus_binding': binding, 'corpus_refs': refs})
        if approval is None or approval['decision'] != 'approve':
            raise ValueError('m1_corpus_approval_required')
        return approval

    try:
        if node == 'review' and attempt:
            session = state.get('sessions', {}).get(attempt.get('session_id'))
            if session is None:
                raise ValueError('m1_council_unknown')
            status = session['status']
            action = {'collecting_initials': 'collect_initials', 'collecting_responses': 'collect_responses',
                      'collecting_final_positions': 'collect_final_positions',
                      'final_positions_complete': 'await_decision_engine'}.get(status, 'await_user')
            approval = corpus_approval()
            if (approval['id'] != session['approval_id']
                    or any(latest.get(ref['logical_path']) != ref for ref in session['input_refs'])):
                raise ValueError('m1_council_input_changed')
            sources = [a for a in state['attempts'] if a['node_id'] == 'hypothesize']
            if (attempt['id'] != session['review_attempt_id'] or not sources
                    or sources[-1]['id'] != session['source_attempt_id']
                    or sources[-1]['status'] != 'review_pending'):
                raise ValueError('m1_council_input_changed')
            binding = store._hash(store._canonical({'packet_version': 1, 'project_id': state['project_id'],
                'source_attempt_id': session['source_attempt_id'], 'approval_id': approval['id'],
                'objects': [{'id': r['id'], 'sha256': r['sha256']} for r in session['input_refs']],
                'configuration': {k: state[k] for k in ('topic', 'profile', 'content_origin')}}))
            if binding != session['input_binding']:
                raise ValueError('m1_council_input_changed')
            if action == 'await_decision_engine':
                reasons = ['All final positions are recorded; a later decision engine must evaluate progression.']
        else:
            inputs, missing = _inputs(state, node, head['objects'])
            if missing:
                action = 'supply_inputs'
                reasons = ['Required registered inputs are missing: ' + ', '.join(missing)]
            elif attempt:
                packet = _packet(state, attempt)
                if node == 'hypothesize' and status == 'review_pending':
                    inputs = {**inputs, 'objects': sorted(
                        [r for r in inputs['objects'] if r['logical_path'] != 'hypotheses/hypotheses.json']
                        + [r for r in packet['inputs']['objects'] if r['logical_path'] == 'hypotheses/hypotheses.json'],
                        key=lambda r: (r['id'], r['sha256']))}
                if packet['packet_version'] != PACKET_VERSION or packet['input_binding'] != _binding(inputs):
                    action, reasons = 'await_user', ['Inputs changed; the current packet requires a new authorized attempt.']
                elif status in ('prepared', 'draft_invalid'):
                    action = 'write_outputs' if status == 'prepared' else 'correct_outputs'
                elif status == 'review_pending':
                    action, reasons = 'await_review', ['Structural registration is complete; independent review or council is required before progression.']
                elif status == 'awaiting_user':
                    action, reasons = 'await_user', ['The initial submission and two draft corrections are exhausted. User judgment is required.']
                else:
                    action, reasons = 'await_transition', ['Current attempt requires a recorded transition before further authoring.']
            elif node in ('review', 'handoff'):
                action, reasons = 'await_engine', ['This node requires its later-task engine.']
            if node == 'extract':
                try:
                    corpus_approval()
                except ValueError:
                    action = 'await_approval'
                    reasons = ['Current corpus requires an explicit user approval; prior or rejected decisions do not authorize extraction.']
    except (ValueError, KeyError) as exc:
        action, reasons = 'await_user', [str(exc)]
    budget = budget_status(state)
    decision = next((d for d in state.get('decisions', [])
                     if attempt and d['id'] == attempt.get('decision_id')), None)
    if decision is not None and status == 'decided':
        if decision['next_action'] == 'return':
            if not reasons:
                action = 'plan_return'
            if budget['exhausted']:
                action = 'await_user'
                reasons.append('m1_return_budget_exhausted')
        reasons.append(decision['rationale'])
    if action == 'await_user' and not reasons:
        reasons = ['Current role/session status requires user action: ' + status]
    return {'action': action, 'status': status, 'wait_reasons': reasons, 'budget': budget}


def build_view(root: Path, *, head_id: str | None = None) -> dict:
    """Return only selected registered state; reject orphan/unreachable commits."""
    base = store._store_path(root)
    if not base.exists():
        raise ValueError('m1_project_not_found')
    history = store._history(base)
    selected = history[-1] if head_id is None else next((item for item in history if item[0] == head_id), None)
    if selected is None:
        raise ValueError('m1_view_head_not_reachable')
    head = store._receipt(*selected)
    state = head['state']
    missing = []
    missing_keys = set()
    def absent(owner, reference_id, reason):
        key = (owner, reference_id, reason)
        if key not in missing_keys:
            missing_keys.add(key)
            missing.append({'owner_id': owner, 'reference_id': reference_id, 'reason': reason})

    refs = {ref['id']: ref for ref in state.get('artifacts', [])}
    if len(refs) != len(state.get('artifacts', [])):
        raise ValueError('m1_view_artifact_id_duplicate')
    contents = {}
    artifacts, versions = [], {}
    for ref in refs.values():
        if head['objects'].get(ref['sha256']) != {'sha256': ref['sha256'], 'size': ref['size']}:
            absent(ref['id'], ref['id'], 'Exact artifact object is not registered at selected HEAD.')
            continue
        digest = ref['sha256']
        if digest not in contents:
            data = store._read_file(base / 'objects' / digest)
            if store._hash(data) != digest or len(data) != ref['size']:
                raise ValueError('m1_store_corrupt')
            contents[digest] = data
        try:
            text = contents[digest].decode('utf-8')
        except UnicodeError:
            text = None
        path = ref['logical_path']
        record = {**deepcopy(ref), 'registered': True, 'projection': False,
                  'registration_status': 'committed', 'host_provenance_status': 'not_observed',
                  'provenance_status': ref.get('provenance_status', 'declared_only'),
                  'content_origin': state['content_origin'], 'kind': 'registered_artifact', 'title': path,
                  'content': text[:PREVIEW_CHARACTERS] if text is not None else '',
                  'content_truncated': text is not None and len(text) > PREVIEW_CHARACTERS,
                  'content_length': len(text) if text is not None else None,
                  'content_status': 'utf8_preview' if text is not None else 'non_utf8',
                  'access_level': 'registered object'}
        artifacts.append(record)
        if path != 'hypotheses/hypotheses.json':
            continue
        try:
            candidates = json.loads(contents[digest], object_pairs_hook=store._unique_pairs)['hypotheses']
        except (ValueError, KeyError, TypeError):
            absent(ref['id'], ref['id'], 'Registered hypothesis JSON cannot be decoded; no alternative version substituted.')
            continue
        for index, candidate in enumerate(candidates):
            identifier = f'{quote(ref["id"], safe="")}/hypothesis/{quote(candidate["id"], safe="")}/r{candidate["revision"]}'
            projected = {**deepcopy(candidate), 'id': identifier, 'original_id': candidate['id'],
                'hypothesis_id': candidate['id'], 'kind': 'hypothesis', 'projection': True, 'registered': False,
                'source_artifact_id': ref['id'], 'source_artifact_sha256': digest,
                'source_json_pointer': f'/hypotheses/{index}',
                'registration_status': 'projection_of_committed_artifact',
                'provenance_status': candidate.get('provenance_status', 'declared_only'),
                'host_provenance_status': 'not_observed', 'content_origin': state['content_origin']}
            versions[(ref['id'], candidate['id'], candidate['revision'])] = projected
            artifacts.append(projected)
    visible_ids = {a['id'] for a in artifacts if a['registered']}
    raw_sessions = state.get('sessions', {})
    sessions = [_session_view(s) for s in raw_sessions.values()]
    session_sources = {s['id']: [r['id'] for r in s['input_refs'] if r['logical_path'] == 'hypotheses/hypotheses.json']
                       for s in sessions}
    def exact_version(session_id, target, owner):
        sources = session_sources.get(session_id, [])
        if len(sources) != 1:
            absent(owner, session_id, 'Exact session hypothesis source is missing or ambiguous.')
            return None
        source = sources[0]
        value = versions.get((source, target['id'], target['revision']))
        if value is None:
            absent(owner, source, 'Exact hypothesis revision is absent from its pinned source artifact.')
        return value

    issues, responses = [], []
    for session in sessions:
        # Already scoped copies are used for threads; there is no fallback to a
        # private map when an initial/response/final round has not disclosed.
        threads = build_issue_threads({**session, 'initials': {},
            'responses': session['disclosed_responses'], 'final_positions': session['disclosed_final_positions']})
        roles = {a['id']: a['role_id'] for a in session['assignments']}
        for thread in threads:
            issue = {**thread['issue'], **{key: value for key, value in thread.items() if key not in ('issue', 'responses')},
                     'response_ids': [r['id'] for r in thread['responses']], 'target_version_ids': []}
            for target in issue.get('target_refs', []):
                version = exact_version(session['id'], target, issue['id'])
                if version:
                    issue['target_version_ids'].append(version['id'])
            issues.append(issue)
        for bundle in session['disclosed_responses']:
            responses.extend({**r, 'session_id': session['id'], 'role_id': roles.get(r['assignment_id']),
                              'role_label': roles.get(r['assignment_id'], r['assignment_id']),
                              'stance_label': r['stance'], 'provenance_status': bundle.get('provenance_status', 'declared_only'),
                              'content_origin': session['content_origin']} for r in bundle['responses'])

    transitions = [_scoped(t, t['session_id']) for t in state.get('transitions', [])]
    decisions = []
    for raw in state.get('decisions', []):
        sid = raw['session_id']
        def cited(value):
            if type(value) is list:
                return [ref for item in value for ref in cited(item)]
            if type(value) is dict:
                return list(value.get('evidence_refs', [])) + [ref for key, item in value.items()
                    if key != 'evidence_refs' for ref in cited(item)]
            return []
        decision = {**_scoped(raw, sid), 'node_id': 'review', 'title': raw.get('title', raw['id']),
                    'registration_status': 'committed', 'host_provenance_status': 'not_observed',
                    'response_ids': [r['id'] for r in responses if r['session_id'] == sid],
                    'evidence_refs': list(dict.fromkeys(cited(raw))), 'hypothesis_versions': []}
        targets = []
        for disposition in decision['hypothesis_dispositions']:
            version = exact_version(sid, disposition['hypothesis_ref'], decision['id'])
            disposition['hypothesis_version_id'] = version['id'] if version else None
            if version:
                decision['hypothesis_versions'].append(version['id'])
                targets.append(version)
        # Only the returned attempt named by this decision can contribute a
        # child. Matching parent_revision alone elsewhere never links a future.
        for transition in transitions:
            if transition['decision_id'] != raw['id'] or transition['target_node_id'] != 'hypothesize':
                continue
            for version in versions.values():
                source = refs[version['source_artifact_id']]
                if source['producer_attempt_id'] != transition['to_attempt_id']:
                    continue
                if any(version['hypothesis_id'] == parent['hypothesis_id']
                       and version.get('parent_revision') == parent['revision'] for parent in targets):
                    if version['id'] not in decision['hypothesis_versions']:
                        decision['hypothesis_versions'].append(version['id'])
        decisions.append(decision)

    attempts = deepcopy(state['attempts'])
    for attempt in attempts:
        for field in ('input_refs', 'output_refs'):
            attempt[field] = [ref['id'] if type(ref) is dict else ref for ref in attempt.get(field, [])]
    graph = describe_graph()
    for node in graph['nodes']:
        role = describe_roles(node['id'])
        candidates = [a for a in attempts if a['node_id'] == node['id']]
        node.update(status=candidates[-1]['status'] if candidates else 'pending',
                    current=node['id'] == state['current_node_id'],
                    question=role['purpose'], acceptance=role['purpose'],
                    roles=[r['role_id'] for r in role['roles']], inputs=role['inputs'], outputs=role['outputs'])
    resumed = _resume(head, contents)
    waits = resumed['wait_reasons']
    view = {**store._VERSION, 'head_id': head['id'], 'data_origin': 'registered',
            'content_origin': state['content_origin'], 'current_node_id': state['current_node_id'],
            'project': {'id': state['project_id'], 'title': state['topic'],
                        **{key: state[key] for key in ('topic', 'profile', 'content_origin')}},
            'nodes': graph['nodes'], 'edges': graph['edges'], 'attempts': attempts,
            'artifacts': artifacts, 'sessions': sessions, 'issues': issues, 'responses': responses,
            'decisions': decisions, 'approvals': deepcopy(state.get('approvals', [])),
            'budget': resumed['budget'], 'budget_changes': deepcopy(state.get('budget_changes', [])),
            'transitions': transitions, 'return_context': transitions[-1] if transitions else None,
            'wait_reasons': waits, 'next_actions': [{'node_id': state['current_node_id'],
                'action': resumed['action'], 'label': resumed['action'].replace('_', ' '),
                'reason': '\n'.join(waits), 'wait_reasons': waits}], 'missing_references': missing}
    def check_refs(value, owner='view'):
        if type(value) is list:
            for item in value:
                check_refs(item, owner)
        elif type(value) is dict:
            owner = value.get('id', owner)
            for key, items in value.items():
                if key in ('evidence_refs', 'input_refs', 'output_refs', 'corpus_refs') and type(items) is list:
                    for item in items:
                        identifier = item.get('id') if type(item) is dict else item
                        if identifier not in visible_ids:
                            absent(owner, identifier, 'Exact artifact is not visible at selected HEAD; no latest substitution.')
                else:
                    check_refs(items, owner)
    check_refs(view)
    validate_view(view)
    return view
