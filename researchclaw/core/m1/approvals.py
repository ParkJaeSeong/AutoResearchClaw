"""User-declared corpus decisions bound to immutable registered evidence.

Decision history is append-only, with the latest decision for an exact binding
controlling access. Reject revokes an earlier approval for that binding.
Authority is explicitly CLI-declared, not independently authenticated. Approval
never supplies a council decision or changes the current node/attempt status.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from . import store
from .artifacts import read_registered_inputs
from .literature import validate_literature

CORPUS_PATHS = ('scope/goal.md', 'scope/constraints.json', 'scope/questions.json',
                'literature/search_plan.yaml', 'literature/candidates.jsonl',
                'literature/search_log.jsonl', 'literature/shortlist.jsonl',
                'literature/screening_decisions.jsonl')
_APPROVAL_FIELDS = set(store._VERSION) | {'id', 'project_id', 'corpus_binding', 'corpus_refs',
    'decision', 'note', 'actor', 'provenance_status', 'content_origin'}


def approval_covers(record: dict, corpus_binding: str) -> bool:
    """Content-only comparison; callers must validate record authority/schema."""
    return record.get('decision') == 'approve' and record.get('corpus_binding') == corpus_binding


def _corpus(root: Path, head: dict) -> dict:
    state = head['state']
    latest = {ref['logical_path']: ref for ref in state.get('artifacts', [])}
    if any(path not in latest for path in CORPUS_PATHS):
        raise ValueError('m1_corpus_inputs_missing')
    refs = [deepcopy(latest[path]) for path in CORPUS_PATHS]
    if len({ref.get('id') for ref in refs}) != len(refs):
        raise ValueError('m1_input_ref_invalid')
    for ref in refs:
        if (not isinstance(ref.get('id'), str) or not ref['id'].strip()
                or not store._is_digest(ref.get('sha256')) or type(ref.get('size')) is not int
                or head['objects'].get(ref['sha256']) != {'sha256': ref['sha256'], 'size': ref['size']}):
            raise ValueError('m1_input_ref_invalid')
    files = read_registered_inputs(root, refs)
    for node in ('search', 'collect', 'screen'):
        if validate_literature(node, files, files):
            raise ValueError('m1_corpus_invalid')
    refs.sort(key=lambda ref: (ref['id'], ref['sha256']))
    binding = store._hash(store._canonical({**store._VERSION, 'project_id': state['project_id'],
        'objects': [{'id': ref['id'], 'sha256': ref['sha256']} for ref in refs]}))
    return {'corpus_binding': binding, 'corpus_refs': refs}


def current_corpus(root: Path) -> dict:
    """Read-only validated corpus binding; drafts never enter state.artifacts."""
    return _corpus(root, store.read_head(root))


def _current_approval(state: dict, corpus: dict) -> dict | None:
    for record in reversed(state.get('approvals', [])):
        if type(record) is not dict:
            raise ValueError('m1_approval_record_invalid')
        if record.get('corpus_binding') != corpus['corpus_binding']:
            continue
        if (set(record) != _APPROVAL_FIELDS
                or type(record.get('schema_version')) is not int
                or any(record.get(key) != value for key, value in store._VERSION.items())
                or record.get('project_id') != state['project_id']
                or not isinstance(record.get('id'), str) or not record['id'].strip()
                or record.get('corpus_refs') != corpus['corpus_refs']
                or record.get('decision') not in ('approve', 'reject')
                or not isinstance(record.get('note'), str) or not record['note'].strip()
                or record.get('actor') != 'user' or record.get('provenance_status') != 'declared_only'
                or record.get('content_origin') != state['content_origin']):
            raise ValueError('m1_approval_record_invalid')
        return deepcopy(record)
    return None


def corpus_status(root: Path, head: dict) -> dict:
    corpus = _corpus(root, head)
    record = _current_approval(head['state'], corpus)
    return {**corpus, 'approval': record,
            'approved': record is not None and approval_covers(record, corpus['corpus_binding'])}


def require_corpus_approval(root: Path, head: dict) -> dict:
    corpus = corpus_status(root, head)
    if not corpus['approved']:
        raise ValueError('m1_corpus_approval_required')
    return corpus


def record_corpus_approval(root: Path, *, corpus_binding: str, decision: str,
                           note: str, command_id: str) -> dict:
    """Record an explicit user decision atomically; exact retries replay receipts."""
    from .packets import _commit, _mutation, _replay, _request
    if (not store._is_digest(corpus_binding) or decision not in ('approve', 'reject')
            or not isinstance(note, str) or not note.strip()):
        raise ValueError('m1_corpus_decision_invalid')
    request = _request(command_id, {'operation': 'record_corpus_approval', 'corpus_binding': corpus_binding,
                                    'decision': decision, 'note': note})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return replay
        head = store.read_head(root)
        corpus = _corpus(root, head)
        if corpus['corpus_binding'] != corpus_binding:
            raise ValueError('m1_corpus_binding_changed')
        record = {**store._VERSION, 'id': f'approval-{uuid4().hex}', 'project_id': head['state']['project_id'],
                  **corpus, 'decision': decision, 'note': note, 'actor': 'user',
                  'provenance_status': 'declared_only', 'content_origin': head['state']['content_origin']}
        head['state'].setdefault('approvals', []).append(record)
        return _commit(root, head, command_id, request, {'approval': deepcopy(record)},
                       event_type='corpus_decided', objects={f"approvals/{record['id']}.json": store._canonical(record)})
