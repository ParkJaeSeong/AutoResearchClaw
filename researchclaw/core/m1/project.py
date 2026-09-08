"""New-project-only M1 lifecycle; no legacy migration or research approvals.

Initial state v1: schema_version, workflow_version, project_id, topic, profile,
max_returns, returns_used (0), current_node_id (scope), attempts ([]), and
content_origin (research or synthetic). Later engines extend state with records.
Identical init reopens current HEAD using genesis configuration for comparison.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ..profiles import load_profile
from ..transactions import project_transaction
from .contracts import NODE_IDS
from . import store


def _check_new_root(root: Path) -> None:
    if root.exists() and not root.is_dir():
        raise ValueError('m1_path_invalid')
    if root.exists() and any(path.name != '.researchclaw' for path in root.iterdir()):
        raise ValueError('m1_project_root_not_empty')
    metadata = store._checked_path(root / '.researchclaw')
    if metadata.exists():
        for path in metadata.iterdir():
            if path.name == 'm1':
                # Another initializer may publish between the preflight checks.
                # Configuration is still compared under the shared lock.
                store._history(store._checked_path(path))
                continue
            if path.name != 'project-transaction.lock' and not path.name.startswith('.m1-init-'):
                raise ValueError('m1_project_root_not_empty')
            store._checked_path(path)


def _mkdir_durable(path: Path) -> None:
    if path.exists():
        # It may exist because an earlier create succeeded but its parent
        # fsync failed. Retry that publication before creating descendants.
        store._fsync_directory(path.parent)
        return
    _mkdir_durable(path.parent)
    path.mkdir(exist_ok=True)
    store._fsync_directory(path.parent)


def init_project(root: Path, *, topic: str, profile: str, max_returns: int,
                 content_origin: str = 'research') -> dict:
    """Create or safely reopen an M1 project with the same original config."""
    if (not isinstance(topic, str) or not topic.strip()
            or type(max_returns) is not int or max_returns < 0
            or content_origin not in ('research', 'synthetic')):
        raise ValueError('m1_project_config_invalid')
    try:
        load_profile(profile)
    except ValueError as exc:
        raise ValueError('m1_project_config_invalid') from exc
    config = {'topic': topic, 'profile': profile, 'max_returns': max_returns,
              'content_origin': content_origin}
    store._canonical(config)
    root = store._checked_path(root)
    base = store._store_path(root)
    if not base.exists():
        _check_new_root(root)
    else:
        store._history(base)
    _mkdir_durable(root)
    _mkdir_durable(base.parent)
    store._checked_path(base.parent / 'project-transaction.lock')
    with project_transaction(root):
        base = store._store_path(root)
        if base.exists():
            history = store._history(base)
            original = history[0][1]['state']
            if any(original.get(key) != value for key, value in config.items()):
                raise ValueError('m1_project_config_conflict')
            store._sync_publication(base)
            return store._receipt(*history[-1])
        _check_new_root(root)
        # Only a fully durable staged store becomes visible as m1/. Crashed
        # staging directories are neither receipts nor a reason to reset state.
        staging = base.parent / f'.m1-init-{uuid4().hex}'
        staging.mkdir()
        (staging / 'objects').mkdir()
        (staging / 'commits').mkdir()
        state = {**store._VERSION, 'project_id': f'm1-{uuid4().hex}', **config,
                 'returns_used': 0, 'current_node_id': NODE_IDS[0], 'attempts': []}
        event = {**store._VERSION, 'type': 'project_initialized', 'payload': config}
        result = store._publish(staging, parent=None, command_id='init', state=state,
                                event=event, objects={}, inputs={})
        store._history(staging)
        os.replace(staging, base)
        store._fsync_directory(base.parent)
        return result


def _resume_project(root: Path, head: dict) -> dict:
    """Report the current work and gates from verified HEAD, without mutation."""
    from .packets import PACKET_VERSION, _binding, _current_attempt, _inputs, _packet

    state = head['state']
    node_id = state['current_node_id']
    if node_id == 'review' and _current_attempt(state) is not None:
        from .council import resume_council
        return resume_council(root, head)
    inputs, missing = _inputs(state, node_id, head['objects'])
    attempt = _current_attempt(state)
    status = 'ready' if attempt is None else attempt['status']
    action = 'prepare_node'
    reasons = []
    if missing:
        reasons = ['Required registered inputs are missing: ' + ', '.join(missing)]
        action = 'supply_inputs'
    elif attempt is not None:
        packet = _packet(state, attempt)
        binding_inputs = inputs
        if node_id == 'hypothesize' and status == 'review_pending':
            # The newly registered cumulative hypotheses are the output of this
            # packet. Its consumed prior hypotheses remain pinned; upstream
            # inputs must still match before advertising independent review.
            binding_inputs = {**inputs, 'objects': sorted(
                [r for r in inputs['objects'] if r['logical_path'] != 'hypotheses/hypotheses.json']
                + [r for r in packet['inputs']['objects'] if r['logical_path'] == 'hypotheses/hypotheses.json'],
                key=lambda r: (r['id'], r['sha256']))}
        if packet['packet_version'] != PACKET_VERSION or packet['input_binding'] != _binding(binding_inputs):
            reasons = ['Inputs changed; the current packet requires a new authorized attempt.']
            action = 'await_user'
        elif status in ('prepared', 'draft_invalid'):
            action = 'write_outputs' if status == 'prepared' else 'correct_outputs'
        elif status == 'review_pending':
            reasons = ['Structural registration is complete; independent review or council is required before progression.']
            action = 'await_review'
        elif status == 'awaiting_user':
            reasons = ['The initial submission and two draft corrections are exhausted. User judgment is required.']
            action = 'await_user'
        else:
            reasons = ['Current attempt requires a recorded transition before further authoring.']
            action = 'await_transition'
    elif node_id in ('review', 'handoff'):
        reasons = ['This node requires its later-task engine.']
        action = 'await_engine'

    corpus = None
    if node_id in ('screen', 'extract'):
        from .approvals import corpus_status
        try:
            corpus = corpus_status(root, head)
        except ValueError as exc:
            corpus = {'approved': False, 'error': str(exc)}
        if node_id == 'extract' and not corpus['approved']:
            action = 'await_approval'
            reasons = ['Current corpus requires an explicit user approval; prior or rejected decisions do not authorize extraction.']
    return {**store._VERSION, 'head_id': head['id'], 'current_node_id': node_id,
            'corpus': corpus,
            'status': status, 'action': action, 'wait_reasons': reasons, 'inputs': inputs,
            'current_attempt': attempt, 'content_origin': state['content_origin']}


def resume_project(root: Path) -> dict:
    """Expose work, historical return rationale and all current gates together."""
    from copy import deepcopy
    from .budgets import budget_status

    head = store.read_head(root)
    state = head['state']
    result = _resume_project(root, head)
    result['budget'] = budget_status(state)
    transitions = state.get('transitions', [])
    result['return_context'] = deepcopy(transitions[-1]) if transitions else None
    attempt = result['current_attempt']
    decision_id = attempt.get('decision_id') if attempt else None
    decision = next((d for d in state.get('decisions', []) if d['id'] == decision_id), None)
    result['decision'] = deepcopy(decision)
    context_decision = decision
    if context_decision is None and transitions:
        context_decision = next(d for d in state['decisions'] if d['id'] == transitions[-1]['decision_id'])
    result['unresolved_issues'] = deepcopy([t for t in context_decision['issue_threads']
        if t.get('status') != 'resolved']) if context_decision else []
    if decision is not None and result['status'] == 'decided':
        if decision['next_action'] == 'return':
            if not result['wait_reasons']:
                result['action'] = 'plan_return'
            result['wait_reasons'].append(decision['rationale'])
            if result['budget']['exhausted']:
                result['action'] = 'await_user'
                result['wait_reasons'].append('m1_return_budget_exhausted')
        else:
            result['wait_reasons'].append(decision['rationale'])
    if result['action'] == 'await_user' and not result['wait_reasons']:
        result['wait_reasons'] = ['Current role/session status requires user action: ' + result['status']]
    return result
