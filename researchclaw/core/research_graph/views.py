"""M1 public projection from one verified ancestor; never a raw state export."""
from copy import deepcopy
import base64
import json
from pathlib import Path

from . import commands, migration, store
from .contracts import validate_record
from .councils import _disclosed, _private, _record_ref, _session, _submissions, _phase
from .dependencies import _References, _FIELDS
from .gates import _status, _blocking_scope
from .issues import _Inputs, _require
from .m1_nodes import _assessment_snapshot, _native, _shape, review_node

_NODES = ('scope', 'questions', 'search', 'screen', 'collect', 'extract', 'synthesize', 'hypothesize', 'review')
_LABELS = ('범위', '연구 질문', '문헌 검색', '문헌 선정', '원문 수집', '근거 추출', '근거 종합', '가설', '최종 검토')


def _load(root, head_id=None):
    base = store._store_path(root)
    history = store._history(base)
    current = history[-1][0]
    if head_id is not None:
        index = next((i for i, (head, _) in enumerate(history) if head == head_id), None)
        _require(index is not None, 'research_view_head_unreachable')
        history = history[:index + 1]
    return _assessment_snapshot(commands._hydrate_policy_snapshot(base, history)), current


class _Public:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.inputs = _Inputs(snapshot)
        self.refs = _References(self.inputs)
        self.private_ids, self.private_hashes = _private(self.inputs)
        for body in self.inputs.state.get('council_submissions', {}).values():
            if body['id'] in self.private_ids:
                for item in (body, *body['positions'], *body['issue_proposals']):
                    self.private_ids.add(item['event_id'])
        self.private_tokens = {value.encode() for value in self.private_ids | self.private_hashes}
        # Imported archives are preserved for provenance, not raw viewer roots.
        self.archive_hashes = {digest for _, record in self.inputs.history
                               for alias, digest in record['object_inputs'].items() if alias.startswith('archive/')}
        self.artifacts, self.raw = {}, {}
        self.checked = {}

    def safe(self, value):
        data = store._canonical(value)
        return not any(token in data for token in self.private_tokens)

    def _check(self, ref, visiting=None):
        key = store._canonical(ref).decode()
        if key in self.checked:
            return self.checked[key]
        visiting = set() if visiting is None else visiting
        if key in visiting:
            return True
        visiting.add(key)
        try:
            self.refs.resolve(ref)  # Historical exact versions are permitted.
            data = self.inputs.objects[ref['sha256']]
            if ref['sha256'] in self.archive_hashes or not self.safe(ref) or any(token in data for token in self.private_tokens):
                return False
            try:
                body = json.loads(data)
            except (UnicodeDecodeError, ValueError):
                body = None
            queue = [body]
            while queue:
                item = queue.pop()
                if type(item) is dict:
                    if (item.get('id') in self.inputs.state.get('m1_preparation_evidence', {})
                            and 'content_base64' in item):
                        # Encoded source bytes have the same disclosure boundary
                        # as raw sources, including through indirect references.
                        decoded = base64.b64decode(item['content_base64'], validate=True)
                        if store._hash(decoded) != item['sha256']:
                            return False
                        source_ref = {**ref, 'artifact_id': 'preparation/raw/' + item['sha256'],
                                      'sha256': item['sha256']}
                        if not self._check(source_ref, visiting):
                            return False
                    if set(item) == _FIELDS:
                        if item['project_id'] == self.inputs.project and not self._check(item, visiting):
                            return False
                    else:
                        # Store snapshots and private collection containers are
                        # never public raw objects, even through an alias wrapper.
                        if set(item) & {'_issue_context', '_command_request', 'council_submissions', 'source_archive'}:
                            return False
                        if 'state' in item and ('events' in item or 'objects' in item):
                            return False
                        queue.extend(item.values())
                elif type(item) is list:
                    queue.extend(item)
            self.checked[key] = True
            return True
        except (ValueError, KeyError, TypeError):
            self.checked[key] = False
            return False
        finally:
            visiting.remove(key)

    def admit(self, ref, label=None):
        if not self._check(ref):
            return None
        identity = 'a-' + store._hash(store._canonical(ref))
        if identity in self.artifacts:
            return identity
        data = self.inputs.objects[ref['sha256']]
        try:
            body = json.loads(data)
            media = 'application/json; charset=utf-8'
        except (UnicodeDecodeError, ValueError):
            body = None
            media = 'text/plain; charset=utf-8'
        self.artifacts[identity] = dict(id=identity, ref=ref, label=label or ref['artifact_id'], media_type=media,
            raw_url=f"/api/artifacts/{identity}?head={self.snapshot['id']}")
        self.raw[identity] = data
        self.follow(body)
        return identity

    def follow(self, value):
        if type(value) is dict:
            if set(value) == _FIELDS:
                if value['project_id'] == self.inputs.project:
                    self.admit(value)
            else:
                for item in value.values():
                    self.follow(item)
        elif type(value) is list:
            for item in value:
                self.follow(item)

    def entry(self, collection, record, kind=None, alias=None):
        if not self.safe(record):
            return None
        record = self.inputs.registered(collection, record['id'], kind)
        ref = _record_ref(self.inputs, collection, record)
        if alias:
            ref['artifact_id'] = alias
        artifact_id = self.admit(ref)
        if artifact_id is None:
            return None
        return dict(record=deepcopy(record), ref=ref, artifact_id=artifact_id)

    def assessment(self, action):
        try:
            result = action()
            if not self.safe(result):
                return dict(ready=False, reason_codes=['public_evidence_unavailable'], required_actions=[])
            self.follow(result)
            return result
        except (ValueError, KeyError) as error:
            code = str(error)
            if not code.replace('_', '').isalnum():
                code = 'public_assessment_unavailable'
            return dict(ready=False, reason_codes=[code], required_actions=[f'Address {code} before advancing.'])


def _project(snapshot, current_head):
    public = _Public(snapshot); inputs = public.inputs; state = inputs.state
    head = snapshot['id']
    view = {**store._VERSION, 'head_id': head, 'current_head_id': current_head, 'project_id': inputs.project,
        'content_origin': state['content_origin'], 'object_count': len(snapshot['objects']), 'event_count': len(snapshot['events']),
        **migration.import_summary(snapshot),
        'project': dict(id=inputs.project, topic=state.get('topic', '가져온 M1 연구'), content_origin=state['content_origin']),
        'milestones': [dict(id='M1', status='active'), dict(id='M2', status='unavailable'), dict(id='M3', status='unavailable')],
        'heads': [dict(head_id=h, parent_head_id=r['parent'], selected=h == head) for h, r in inputs.history],
        'nodes': [], 'revisions': [], 'councils': [], 'issues': [], 'transitions': [],
        'verifications': [], 'results': [], 'source_checks': [], 'approvals': [], 'dependencies': [], 'handoffs': [],
        'external_evidence': [], 'external_reviews': [], 'external_decisions': [], 'external_questions': [],
        'work_episodes': [], 'work_followups': [],
        'evidence': None, 'corpus': None, 'accounting': None, 'reason_codes': [], 'required_actions': []}
    # Registration order, not UUID sort order, is the actual revision/move order.
    prior_node = None
    for at_head, commit in inputs.history:
        event = commit['events'][-1]
        if event['type'] != 'm1_node_registered':
            continue
        payload = {k: v for k, v in event['payload'].items() if k != '_command_request'}
        record = inputs.registered('m1_node_revisions', payload['revision_id'])
        _require(_shape(record, inputs.project), 'research_view_node_invalid')
        _native(inputs, 'm1_node_revisions', record, 'm1_node_registered', payload)
        entry = public.entry('m1_node_revisions', record, alias=f"m1/nodes/{record['node']}")
        if entry is None:
            view['reason_codes'].append('public_evidence_unavailable')
            continue
        entry.update(current=state.get('m1_node_heads', {}).get(record['node']) == record['id'],
                     previous_ref=json.loads(record['previous_ref_key']) if record['previous_ref_key'] else None)
        view['revisions'].append(entry)
        view['transitions'].append(dict(head_id=at_head, from_node=prior_node, to_node=record['node'],
                                        revision_id=record['id'], attempt=record['attempt']))
        prior_node = record['node']
    visible_revisions = {row['record']['id'] for row in view['revisions']}
    for node, label in zip(_NODES, _LABELS):
        identity = state.get('m1_node_heads', {}).get(node)
        result = public.assessment(lambda: review_node(snapshot, node)) if identity in visible_revisions else {
            'ready': False, 'reason_codes': ['node_missing'] if identity is None else ['public_evidence_unavailable'], 'required_actions': []}
        status = 'ready' if result['ready'] else ('not_started' if identity is None else
            ('stale' if any('stale' in r for r in result['reason_codes']) else 'awaiting_input'))
        view['nodes'].append(dict(id=node, label=label, status=status,
            current_revision_id=identity if identity in visible_revisions else None,
            revision_ids=[r['record']['id'] for r in view['revisions'] if r['record']['node'] == node],
            reason_codes=result['reason_codes'], required_actions=result['required_actions'], next_node=result.get('next_node')))
    for record in state.get('councils', {}).values():
        _native(inputs, 'councils', record, 'council_prepared', dict(council_id=record['id'], session_id=record['session_id']))
        session = _session(inputs, record); records = _submissions(inputs, record)
        disclosed = _disclosed(inputs, record, records)
        for rows in disclosed.values():
            for row in rows:
                sub = row['submission']
                _native(inputs, 'council_submissions', sub, 'council_submission_registered',
                        dict(submission_id=sub['id'], session_id=record['session_id'], phase=sub['phase']))
        entry = dict(id=record['id'], session_id=record['session_id'], node=record['node'], attempt=record['attempt'],
            phase=_phase(inputs, record, records), required_roles=record['required_roles'],
            submitted_counts={p: len(rows) for p, rows in records.items()}, input_binding=session['input_binding'],
            authors=[inputs.assignment(i) for i in record['author_assignment_ids']],
            participants=[{**inputs.assignment(i), 'council_role': role} for role, i in record['required_roles'].items()],
            disclosed_initials=disclosed['initial'], disclosed_responses=disclosed['response'], disclosed_finals=disclosed['final'],
            isolation_level='instructions_only', identity_provenance='declared_only', content_origin=record['content_origin'])
        if public.safe(entry) and public._check(session['input_binding']):
            # No own_submissions projection exists in the public viewer.
            view['councils'].append(entry); public.follow(entry)
            public.entry('councils', record)
    for record in state.get('issues', {}).values():
        if not public.safe(record):
            continue
        _require(not validate_record('Issue', record), 'research_view_issue_invalid')
        imported = record['id'] in state.get('imported_issue_states', {})
        events = []
        for at_head, commit in inputs.history:
            event = commit['events'][-1]
            if event['type'] != 'issue_event' or event['payload'].get('issue_id') != record['id']:
                continue
            body = {k: v for k, v in event['payload'].items() if k != '_command_request'}
            _require(not validate_record('IssueEvent', body), 'research_view_issue_invalid')
            ref = dict(project_id=inputs.project, head_id=at_head, artifact_id=f"issue-events/{body['id']}",
                       sha256=store._hash(store._canonical(body)))
            if public.safe(body) and public.admit(ref):
                events.append(dict(record=body, ref=ref, head_id=at_head))
        entry = public.entry('issues', record, 'Issue') if not imported else None
        if imported and not events:
            status = 'pending_policy_revalidation'
        else:
            status, _ = _status(inputs, record)
        if imported:
            # A03's authenticated public Issue projection is intentionally not
            # materialized as a new native object or an archive raw-byte grant.
            entry = dict(record=deepcopy(record), ref=None, artifact_id=None)
        if entry:
            scopes = _blocking_scope(inputs, record)
            entry.update(effective_blocking_scope=scopes, scope_changed=scopes != record['blocking_scope'])
            entry.update(status=status, imported_pending=imported and not events, history=events,
                         import_context=deepcopy(state.get('imported_issue_states', {}).get(record['id'])))
            if public.safe(entry):
                view['issues'].append(entry)
    for output, collection, kind in (
        ('verifications', 'verifications', 'Verification'), ('results', 'verification_results', 'VerificationResult'),
        ('source_checks', 'm1_source_observations', None), ('approvals', 'approval_receipts', None),
        ('approvals', 'approval_bindings', 'ApprovalBinding'), ('dependencies', 'dependencies', 'Dependency')):
        for record in state.get(collection, {}).values():
            entry = public.entry(collection, record, kind)
            if entry:
                entry['kind'] = collection
                view[output].append(entry)
    from .handoffs import handoff_status
    for record in state.get('handoffs', {}).values():
        entry = public.entry('handoffs', record, 'Handoff')
        if entry:
            entry['assessment'] = public.assessment(lambda: handoff_status(snapshot, handoff_id=record['id']))
            view['handoffs'].append(entry)
    if 'screen' in state.get('m1_node_heads', {}):
        from .m1_evidence import current_evidence
        from .m1_search import corpus_status
        view['evidence'] = public.assessment(lambda: current_evidence(snapshot))
        view['corpus'] = public.assessment(lambda: corpus_status(snapshot))
    if 'topic' in state:
        from .work_accounting import accounting_status
        view['accounting'] = public.assessment(lambda: accounting_status(snapshot))
    for key in ('evidence', 'corpus', 'accounting'):
        if view[key]:
            view['reason_codes'].extend(view[key].get('reason_codes', []))
            view['required_actions'].extend(view[key].get('required_actions', []))
    view['reason_codes'] = list(dict.fromkeys(view['reason_codes']))
    view['required_actions'] = list(dict.fromkeys(view['required_actions']))
    from .source_intake import captured_records
    view['source_captures'] = []
    for record in captured_records(snapshot):
        entry = public.entry('source_captures', record)
        if entry is not None:
            entry['usage_status'] = 'unassessed'
            view['source_captures'].append(entry)
    from .external_evidence import evidence_records, _authored
    evidence = evidence_records(snapshot)
    by_previous = {store._canonical(record['previous_ref']).decode(): record for record in evidence if record['previous_ref']}
    def duplicate_key(record):
        qa = {key: value for key, value in record['qa'].items()
              if key not in {'id', 'project', 'file_sha256', 'missing_fields'}}
        return store._canonical(qa)
    duplicate_groups = {}
    for record in evidence:
        duplicate_groups.setdefault(duplicate_key(record), []).append(record)
    for record in evidence:
        entry = public.entry('external_evidence', record)
        if entry is not None:
            newer = by_previous.get(store._canonical(entry['ref']).decode())
            entry.update(latest=newer is None,
                         newer_ref=None if newer is None else _record_ref(inputs, 'external_evidence', newer),
                         possible_duplicate_refs=[_record_ref(inputs, 'external_evidence', other)
                             for other in duplicate_groups[duplicate_key(record)]
                             if other['atlas_qa_id'] != record['atlas_qa_id']])
            view['external_evidence'].append(entry)
    for output, collection, event_type, event_key in (
        ('external_reviews', 'external_reviews', 'external_review_recorded', 'record_id'),
        ('external_decisions', 'external_decisions', 'external_decision_recorded', 'record_id'),
        ('external_questions', 'external_questions', 'external_question_recorded', 'record_id')):
        for record in state.get(collection, {}).values():
            _authored(inputs, collection, record, event_type)
            entry = public.entry(collection, record)
            if entry is not None:
                view[output].append(entry)
    from .m1_preparation import project_preparations
    view['m1_preparations'] = project_preparations(snapshot, public)
    # project_preparations already replays both typed collections, including
    # sources not yet attached to a preparation declaration.
    for collection in ('m1_preparation_evidence', 'm1_preparation_verifications'):
        view[collection] = []
        for record in state.get(collection, {}).values():
            entry = public.entry(collection, record)
            if entry is not None:
                if collection == 'm1_preparation_evidence':
                    raw_ref = {**entry['ref'], 'artifact_id': 'preparation/raw/' + record['sha256'],
                               'sha256': record['sha256']}
                    raw_id = public.admit(raw_ref, '준비 자료 원문')
                    if raw_id is not None:
                        entry['source_ref'] = raw_ref
                        entry['source_artifact_id'] = raw_id
                view[collection].append(entry)
    from .m1_evidence_basis import project_bases
    view['m1_evidence_bases'] = project_bases(snapshot, public)
    from .work_episodes import public_episodes
    view['work_episodes'] = public_episodes(snapshot)
    from .execution_view import public_execution
    view['executions'] = public_execution(snapshot)
    from .work_followups import public_followups
    view['work_followups'] = public_followups(snapshot)
    from .issue_impacts import impact_records, current_impact_ids
    impacts = impact_records(snapshot)
    current_ids = current_impact_ids(snapshot, impacts)
    view['issue_impacts'] = []
    for record in impacts:
        entry = public.entry('issue_impacts', record)
        if entry is not None:
            entry['current'] = record['id'] in current_ids
            view['issue_impacts'].append(entry)
    from .issue_scopes import _proposal
    view['scope_proposals'], view['scope_changes'] = [], []
    for record in state.get('issue_scope_proposals', {}).values():
        entry = public.entry('issue_scope_proposals', record)
        if entry is not None:
            _proposal(inputs, entry['ref'])
            view['scope_proposals'].append(entry)
    for record in state.get('issue_scope_changes', {}).values():
        entry = public.entry('issue_scope_changes', record)
        if entry is not None:
            entry['active_issue_ids'] = [identity for identity, proposal_id in getattr(inputs, '_scope_proposal_ids', {}).items()
                                         if proposal_id == record['proposal_ref']['artifact_id']]
            view['scope_changes'].append(entry)
    view['artifacts'] = list(public.artifacts.values())
    return deepcopy(view), public.raw


def build_view(root: Path, *, head_id: str | None = None) -> dict:
    """Read-only M1 projection; head_id must belong to current verified ancestry."""
    snapshot, current = _load(root, head_id)
    return _project(snapshot, current)[0]


def read_artifact(root: Path, *, artifact_id: str, head_id: str | None = None) -> bytes:
    """Resolve an opaque raw ID from a freshly computed selected-head allowlist."""
    snapshot, current = _load(root, head_id)
    _, allowed = _project(snapshot, current)
    _require(type(artifact_id) is str and artifact_id in allowed, 'research_view_artifact_unavailable')
    return allowed[artifact_id]
