"""Immutable, prospective return plans bound to one verified current HEAD.

The authorized target's current output artifacts are the proposed revision
boundary. Consumers are found by exact artifact identity, never node order or
logical-path similarity. Affected means reconsider on revision, not deletion.
No artifacts, approval, attempts, budgets or files are changed by planning.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from . import store
from .approvals import corpus_status
from .contracts import allowed_return_targets
from .council import _current, _session
from .issues import build_issue_threads
from .packets import _current_attempt
from .roles import describe_roles

_REASONS = {'scope': 'scope_change', 'questions': 'question_change',
            'search': 'search_change', 'collect': 'source_change',
            'screen': 'corpus_selection_change', 'extract': 'extraction_error',
            'synthesize': 'synthesis_revision', 'hypothesize': 'hypothesis_revision'}
# Only reject explicit global reset language. Words such as "delete all"
# may describe a legitimate edit within one hypothesis. The authorized target
# and exact artifact dependency closure enforce the actual revision boundary.
_BLANKET_RESET = re.compile(
    r'\b(?:reset|restart|redo|clear|delete)\s+'
    r'(?:all\s+(?:stages|nodes)|(?:the\s+)?(?:entire|whole)\s+(?:project|workflow|graph))\b'
    r'|^\s*(?:reset|restart|redo|clear|delete)\s+(?:all|everything)\s*[.!]?\s*$'
    r'|^\s*전체\s*초기화\s*[.!]?\s*$|모든\s*단계\s*초기화', re.IGNORECASE)


def affected_attempts(attempts: list[dict], changed_artifact_ids: set[str]) -> tuple[str, ...]:
    """Find the fixed-point consumer closure of normalized artifact ID lists."""
    changed = set(changed_artifact_ids)
    affected = set()
    while True:
        added = False
        for attempt in attempts:
            if attempt['id'] not in affected and changed.intersection(attempt['input_refs']):
                affected.add(attempt['id'])
                changed.update(attempt['output_refs'])
                added = True
        if not added:
            return tuple(sorted(affected))


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _project_attempts(head: dict) -> list[dict]:
    """Resolve full registered refs before projecting to dependency IDs."""
    artifacts = head['state'].get('artifacts', [])
    registry = {ref['id']: ref for ref in artifacts}
    if len(registry) != len(artifacts):
        raise ValueError('m1_input_ref_invalid')
    projected = []
    seen = set()
    for attempt in head['state']['attempts']:
        if not _text(attempt.get('id')) or attempt['id'] in seen:
            raise ValueError('m1_input_ref_invalid')
        seen.add(attempt['id'])
        value = {'id': attempt['id']}
        for key in ('input_refs', 'output_refs'):
            refs = attempt[key]
            ids = []
            for ref in refs:
                if (type(ref) is not dict or not _text(ref.get('id'))
                        or store._canonical(registry.get(ref['id'])) != store._canonical(ref)
                        or head['objects'].get(ref.get('sha256')) !=
                            {'sha256': ref.get('sha256'), 'size': ref.get('size')}
                        or (key == 'output_refs' and ref.get('producer_attempt_id') != attempt['id'])):
                    raise ValueError('m1_input_ref_invalid')
                ids.append(ref['id'])
            value[key] = ids
        projected.append(value)
    return projected


def plan_return(root: Path, *, decision_id: str, target_node_id: str, issue_ids: list[str]) -> dict:
    """Describe the registered decision's return without applying any change.

    ``input_head`` and the hash bind the entire proposed plan to this snapshot.
    Future application must compare both against a newly computed current plan.
    Target output refs are prospective changes, not assertions that bytes have
    already changed. Approval effects describe that future revision separately
    from the current, still-preserved corpus approval.
    """
    head = store.read_head(root)
    state = head['state']
    matches = [d for d in state.get('decisions', []) if d.get('id') == decision_id]
    if not _text(decision_id) or len(matches) != 1 or matches[0].get('next_action') != 'return':
        raise ValueError('m1_return_not_authorized')
    decision = matches[0]
    session = _session(state, decision['session_id'])
    _current(root, head, session)
    attempt = _current_attempt(state)
    if (session.get('status') != 'decided' or session.get('decision_id') != decision_id
            or attempt.get('decision_id') != decision_id or attempt.get('status') != 'decided'
            or decision.get('review_attempt_id') != attempt['id']
            or decision.get('source_attempt_id') != session['source_attempt_id']
            or decision.get('input_binding') != session['input_binding']
            or decision.get('approval_id') != session['approval_id']):
        raise ValueError('m1_return_not_authorized')
    if (not _text(target_node_id) or target_node_id != decision.get('return_target')
            or target_node_id not in allowed_return_targets(attempt['node_id'])):
        raise ValueError('m1_return_target_invalid')
    if (type(issue_ids) is not list or not issue_ids or not all(_text(i) for i in issue_ids)
            or len(set(issue_ids)) != len(issue_ids)):
        raise ValueError('m1_return_issue_invalid')
    frozen = {t['issue']['id']: t for t in decision['issue_threads']}
    current_threads = {t['issue']['id']: t for t in build_issue_threads(session)}
    for issue_id in issue_ids:
        thread = frozen.get(issue_id)
        if (thread is None or issue_id not in decision['issue_ids']
                or thread['issue'].get('session_id') != session['id']
                or store._canonical(thread) != store._canonical(current_threads.get(issue_id))):
            raise ValueError('m1_return_issue_invalid')
    work = decision.get('proposed_work')
    if (type(work) is not list or not work or not all(_text(w) for w in work)
            or any(_BLANKET_RESET.search(w) for w in work) or not _text(decision.get('rationale'))):
        raise ValueError('m1_return_work_required')

    projected = _project_attempts(head)
    latest = {r['logical_path']: r for r in state['artifacts']}
    paths = describe_roles(target_node_id)['outputs']
    if any(path not in latest for path in paths):
        raise ValueError('m1_return_outputs_missing')
    seeds = [latest[path] for path in paths]
    # Require actual registered producers; an unattached checkpoint is not a
    # completed node output that can authorize an arbitrary reset boundary.
    producers = {r['producer_attempt_id'] for r in seeds}
    for ref in seeds:
        if not any(a['id'] == ref['producer_attempt_id'] and a['node_id'] == target_node_id
                   and ref in a['output_refs'] for a in state['attempts']):
            raise ValueError('m1_return_outputs_missing')
    changed = {r['id'] for r in seeds}
    affected = set(affected_attempts(projected, changed)) | producers
    impacted_outputs = changed | {ref for a in projected if a['id'] in affected for ref in a['output_refs']}
    corpus = corpus_status(root, head)
    needs_approval = bool(impacted_outputs.intersection(r['id'] for r in corpus['corpus_refs']))
    approval_id = corpus['approval']['id'] if corpus['approval'] else None
    body = {**store._VERSION, 'input_head': head['id'], 'project_id': state['project_id'],
        'decision_id': decision_id, 'session_id': session['id'], 'from_attempt_id': attempt['id'],
        'target_node_id': target_node_id, 'reason_code': _REASONS[target_node_id],
        'issue_ids': sorted(issue_ids), 'rationale': decision['rationale'], 'proposed_work': deepcopy(work),
        'changed_artifact_ids': sorted(changed), 'affected_attempt_ids': sorted(affected),
        'reusable_attempt_ids': sorted(a['id'] for a in projected if a['id'] not in affected),
        'reusable_artifact_ids': sorted(r['id'] for r in state['artifacts'] if r['id'] not in impacted_outputs),
        'approval_effects': {
            'current': {'approval_id': approval_id, 'corpus_binding': corpus['corpus_binding'],
                        'approved': corpus['approved']},
            'after_change': {'approval_required': needs_approval, 'screen_required': needs_approval,
                'approval_id': None if needs_approval else approval_id,
                'corpus_binding': None if needs_approval else corpus['corpus_binding']}},
        'content_origin': state['content_origin'], 'provenance_status': 'declared_only'}
    digest = store._hash(store._canonical(body))
    # Read-only optimistic check: no mutation lock or fsync may change mtimes.
    if store.read_head(root)['id'] != head['id']:
        raise ValueError('m1_head_conflict')
    return {**body, 'id': 'return-' + digest, 'plan_hash': digest}
