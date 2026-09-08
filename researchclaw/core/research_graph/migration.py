"""Explicit, read-only M1 snapshot import into one prepared graph genesis.

Archive bodies are immutable objects, never a current council projection. UUID5
identities are scoped by original project identity and typed legacy identifiers;
issue identities additionally include the source session. Import status is
metadata awaiting policy revalidation, not an actor-authored IssueEvent.
"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from ..m1 import store as legacy
from ..m1.issues import build_issue_threads
from . import store
from .contracts import validate_record


def _identity(namespace, *parts):
    return str(uuid5(UUID(str(namespace)), store._canonical(list(parts)).decode()))


def _content_origin(value):
    origins = {'research': 'real', 'real': 'real', 'synthetic': 'synthetic', 'mixed': 'mixed'}
    if not isinstance(value, str) or value not in origins:
        raise ValueError('research_graph_import_source_invalid')
    return origins[value]


def _targets(original, session, selected, namespace, source_head, objects):
    targets = original.get('target_refs', [])
    if type(targets) is not list or any(type(t) is not dict or set(t) != {'id', 'revision'}
            or not isinstance(t['id'], str) or not t['id'].strip()
            or type(t['revision']) is not int or t['revision'] < 1 for t in targets):
        raise ValueError('research_graph_import_source_invalid')
    refs, mappings, limitations = [], [], []
    inputs = [r for r in session.get('input_refs', [])
              if r['logical_path'] == 'hypotheses/hypotheses.json']
    candidates, source = [], None
    if len(inputs) == 1:
        matches = [r for r in selected['state'].get('artifacts', []) if r == inputs[0]]
        if len(matches) == 1:
            source = matches[0]
            if selected['objects'].get(source['sha256']) == {'sha256': source['sha256'], 'size': source['size']}:
                try:
                    candidates = json.loads(objects[f"archive/objects/{source['sha256']}"],
                        object_pairs_hook=legacy._unique_pairs)['hypotheses']
                    if type(candidates) is not list:
                        candidates = []
                except (ValueError, KeyError, TypeError, UnicodeError):
                    candidates = []
    for target in targets:
        matches = [(i, value) for i, value in enumerate(candidates) if type(value) is dict
                   and value.get('id') == target['id'] and type(value.get('revision')) is int
                   and value['revision'] == target['revision']]
        if source is None or len(matches) != 1:
            limitations.append(f"Exact target {target['id']} revision {target['revision']} is missing or ambiguous in its pinned session artifact.")
            continue
        ref = dict(project_id=namespace, head_id=source_head, artifact_id=source['id'], sha256=source['sha256'])
        if ref not in refs:
            refs.append(ref)
        mappings.append({'original_target_ref': deepcopy(target), 'snapshot_ref': ref,
                         'source_json_pointer': f'/hypotheses/{matches[0][0]}'})
    if not targets:
        limitations.append('Legacy issue declares no exact target references.')
    return refs, mappings, limitations


def _validate_disclosures(session):
    """Reject shapes legacy projection helpers would silently treat as empty.

    Validate the disclosed boundary only; do not rewrite accepted source data
    or read private submissions into the native issue projection.
    """
    def records(value):
        if type(value) is not list or any(type(member) is not dict for member in value):
            raise ValueError('research_graph_import_source_invalid')
        return value

    def text(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('research_graph_import_source_invalid')

    for initial in records(session.get('disclosed_initials')):
        records(initial.get('open_issues'))
    for bundle in records(session.get('disclosed_responses')):
        records(bundle.get('new_issues'))
        for response in records(bundle.get('responses')):
            text(response.get('issue_id'))
    for position in records(session.get('disclosed_final_positions')):
        text(position.get('assignment_id'))
        for disposition in records(position.get('issue_dispositions')):
            text(disposition.get('issue_id'))
            if disposition.get('status') not in ('open', 'resolved'):
                raise ValueError('research_graph_import_source_invalid')


def _projection(selected, source_root, source_head, commits, objects):
    old = selected['state']
    if (type(old.get('sessions', {})) is not dict
            or type(old.get('attempts', [])) is not list
            or type(old.get('artifacts', [])) is not list
            or any(type(ref) is not dict for ref in old.get('artifacts', []))):
        raise ValueError('research_graph_import_source_invalid')
    source_id = old.get('project_id')
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('research_graph_import_source_invalid')
    namespace = _identity(NAMESPACE_URL, 'researchclaw:m1-archive:v1', source_id)
    project_id = _identity(namespace, 'import', source_root, source_head)
    event_id = _identity(project_id, 'import-event')
    maps = {'attempts': {}, 'sessions': {}, 'issues': {}}
    for attempt in old.get('attempts', []):
        maps['attempts'][attempt['id']] = _identity(namespace, 'attempt', attempt['id'])
    issues, statuses, sessions = {}, {}, {}
    limitations = ['Legacy provenance is declared only; host independence is not inferred.',
                   'Imported councils are read-only archives; policy and approvals require revalidation.']
    for session_id, session in sorted(old.get('sessions', {}).items()):
        if session.get('id') != session_id:
            raise ValueError('research_graph_import_source_invalid')
        session_origin = _content_origin(session.get('content_origin', old['content_origin']))
        maps['sessions'][session_id] = _identity(namespace, 'session', session_id)
        for key in ('source_attempt_id', 'review_attempt_id'):
            attempt_id = session.get(key)
            if not isinstance(attempt_id, str) or not attempt_id.strip():
                raise ValueError('research_graph_import_source_invalid')
            maps['attempts'][attempt_id] = _identity(namespace, 'attempt', attempt_id)
        sessions[session_id] = {'id': maps['sessions'][session_id], 'read_only': True,
            'source_status': session['status'], 'source_attempt_id': session['source_attempt_id'],
            'review_attempt_id': session['review_attempt_id'],
            'source_content_origin': session.get('content_origin', old['content_origin'])}
        _validate_disclosures(session)
        # Never let collect_issues' legacy fallback expose unpublished initials.
        disclosed = {**session, 'initials': {}, 'responses': session.get('disclosed_responses', []),
                     'final_positions': session.get('disclosed_final_positions', [])}
        if session['status'] == 'collecting_initials':
            disclosed['disclosed_initials'] = []
        maps['issues'][session_id] = {}
        for thread in build_issue_threads(disclosed):
            original = thread['issue']
            local_id = original['id']
            if local_id in maps['issues'][session_id]:
                raise ValueError('research_graph_import_duplicate_issue')
            issue_id = _identity(namespace, 'issue', session_id, local_id)
            maps['issues'][session_id][local_id] = issue_id
            target_refs, target_mappings, target_limitations = _targets(
                original, session, selected, namespace, source_head, objects)
            issue = {**store._VERSION, 'project_id': project_id, 'id': issue_id,
                'event_id': event_id, 'producer_id': 'm1-import-v1',
                'content_origin': session_origin,
                'provenance_status': 'declared_only', 'observation_refs': [],
                'origin': {'milestone': 'M1', 'node': 'review',
                    'attempt': maps['attempts'][session['review_attempt_id']], 'local_issue_id': local_id},
                'question': original['question'], 'category': 'other', 'target_refs': target_refs,
                'severity': original['severity'],
                'blocking_scope': ([{'kind': 'node', 'milestone': 'M1', 'target_id': 'review'}]
                                   if original['severity'] == 'blocking' else []),
                'resolution_condition': original['resolution_condition'], 'owner_assignment_id': None}
            if validate_record('Issue', issue):
                raise ValueError('research_graph_import_issue_invalid')
            issues[issue_id] = issue
            statuses[issue_id] = {'source_status': thread['status'],
                'import_state': 'pending_policy_revalidation', 'source_session_id': session_id,
                'source_local_issue_id': local_id,
                'original_target_refs': deepcopy(original.get('target_refs', [])),
                'target_mappings': target_mappings, 'limitations': target_limitations}
    archive = {'format_version': 1, 'source_root': source_root, 'source_project_id': source_id,
        'project_id': namespace, 'head_id': source_head, 'commits': commits,
        'source_content_origin': old['content_origin'],
        'objects': deepcopy(selected['objects']), 'id_map': maps, 'sessions': sessions,
        'read_only': True, 'limitations': limitations}
    state = {**store._VERSION, 'project_id': project_id, 'content_origin': _content_origin(old['content_origin']),
        'issues': issues, 'imported_issue_states': statuses, 'source_archive': archive,
        'sessions': {}, 'issue_events': []}
    event = {**store._VERSION, 'type': 'm1_imported', 'payload': {
        'event_id': event_id, 'source_project_id': source_id, 'source_head': source_head,
        'source_root': source_root, 'issue_count': len(issues)}}
    return state, event


def import_m1(source: Path, target: Path, *, source_head: str, command_id: str) -> dict:
    """Verify selected reachable history and publish its complete archive once.

    Verification reads the source without acquiring a source lock or writing any
    source path. Later source HEAD advances cannot alter this pinned snapshot.
    A retry reconstructs the same genesis even after target HEAD has advanced.
    """
    source, target = store._checked_path(source), store._checked_path(target)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('research_graph_import_paths_overlap')
    if not store._is_digest(source_head):
        raise ValueError('research_graph_import_source_head_invalid')
    base = legacy._store_path(source)
    history = legacy._history(base)
    index = next((i for i, (digest, _) in enumerate(history) if digest == source_head), None)
    if index is None:
        raise ValueError('research_graph_import_source_head_unreachable')
    history = history[:index + 1]
    selected = history[-1][1]
    objects, commits = {}, {}
    for digest, record in history:
        data = legacy._read_file(base / 'commits' / digest / 'record.json')
        # Preserve original bytes while verifying they still encode this record.
        if data != legacy._canonical(record):
            raise ValueError('research_graph_import_source_changed')
        objects[f'archive/commits/{digest}.json'] = data
        commits[digest] = store._hash(data)
    for digest, ref in selected['objects'].items():
        data = legacy._read_file(base / 'objects' / digest)
        if store._hash(data) != digest or len(data) != ref['size']:
            raise ValueError('research_graph_import_source_changed')
        objects[f'archive/objects/{digest}'] = data
    try:
        state, event = _projection(selected, str(source), source_head, commits, objects)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('research_graph_import_source_invalid') from exc
    return store.initialize_record(target, command_id=command_id, state=state, event=event, objects=objects)


def import_summary(head: dict) -> dict:
    """Public allowlist; excludes archived bytes and all council submissions."""
    state = head['state']
    archive = state.get('source_archive')
    if archive is None:
        return {}
    counts = {}
    for value in state['imported_issue_states'].values():
        status = value['source_status']
        counts[status] = counts.get(status, 0) + 1
    return {'import': {'source_project_id': archive['source_project_id'],
        'source_head': archive['head_id'], 'archive_project_id': archive['project_id'],
        'issue_count': len(state['issues']), 'issue_status_counts': counts,
        'import_state': 'pending_policy_revalidation', 'archived_session_count': len(archive['sessions']),
        'archive_read_only': True, 'limitations': archive['limitations']}}
