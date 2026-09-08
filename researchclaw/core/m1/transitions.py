"""Immutable return plans and atomic applications bound to verified current HEAD.

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
    r'|^\s*start\s+over\s*[.!?]*\s*$'
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


def _return_basis(state: dict, plan: dict, inputs: dict) -> str:
    """Ignore new record IDs when research inputs, issue substance and work repeat.

    Consumed prior hypotheses count by content, never their new ArtifactRef ID.
    Text is compared exactly; scientific novelty is not inferred from prose.
    """
    evidence = sorted([ref['logical_path'], ref['sha256']] for ref in inputs['objects'])
    decision = next(d for d in state['decisions'] if d['id'] == plan['decision_id'])
    registry = {ref['id']: ref for ref in state['artifacts']}
    issues = []
    for thread in decision['issue_threads']:
        issue = thread['issue']
        if issue['id'] in plan['issue_ids']:
            detail = {key: issue[key] for key in ('question', 'impact', 'severity', 'resolution_condition')}
            detail['target_refs'] = sorted(issue['target_refs'], key=store._canonical)
            detail['evidence'] = sorted([registry[ref_id]['logical_path'], registry[ref_id]['sha256']]
                                        for ref_id in issue['evidence_refs'])
            issues.append(detail)
    issues.sort(key=store._canonical)
    return store._hash(store._canonical({'target_node_id': plan['target_node_id'],
        'inputs': evidence, 'configuration': inputs['configuration'],
        'issues': issues, 'proposed_work': sorted(plan['proposed_work'])}))


def apply_return(root: Path, *, plan: dict, command_id: str) -> dict:
    """Atomically publish a validated plan, new draft and one budget debit."""
    from .budgets import budget_status
    from .packets import (_commit, _inputs, _mutation, _new_draft, _packet, _replay, _request,
                          _work_directory)

    request = _request(command_id, {'operation': 'apply_return', 'plan': plan})
    plan = request['plan']
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            _work_directory(root, replay['packet'])
            return replay
        head = store.read_head(root)
        state = head['state']
        if type(plan) is not dict or not all(key in plan for key in
                ('input_head', 'decision_id', 'target_node_id', 'issue_ids')):
            raise ValueError('m1_return_plan_invalid')
        if plan['input_head'] != head['id']:
            raise ValueError('m1_head_conflict')
        current = plan_return(root, decision_id=plan['decision_id'],
                              target_node_id=plan['target_node_id'], issue_ids=plan['issue_ids'])
        if store._canonical(current) != store._canonical(plan):
            raise ValueError('m1_return_plan_invalid')
        if budget_status(state)['exhausted']:
            raise ValueError('m1_return_budget_exhausted')
        node = plan['target_node_id']
        inputs, missing = _inputs(state, node, head['objects'])
        if missing:
            raise ValueError('m1_inputs_missing: ' + ', '.join(missing))
        basis = _return_basis(state, plan, inputs)
        attempts = {attempt['id']: attempt for attempt in state['attempts']}
        for previous in state.get('transitions', []):
            # The committed packet pins historical input refs AND configuration.
            # Cached hashes are audit data, never a substitute for that basis.
            previous_inputs = _packet(state, attempts[previous['to_attempt_id']])['inputs']
            if _return_basis(state, previous, previous_inputs) == basis:
                raise ValueError('m1_no_new_basis')
        prior = [a for a in state['attempts'] if a['node_id'] == node][-1]
        attempt, packet = _new_draft(state, node, inputs, prior=prior)
        transition = {**deepcopy(plan), 'to_attempt_id': attempt['id'], 'basis_hash': basis,
                      'returns_used_before': state['returns_used'],
                      'returns_used_after': state['returns_used'] + 1}
        attempt['return_transition_id'] = transition['id']
        state.setdefault('transitions', []).append(transition)
        state['current_node_id'] = node
        state['returns_used'] += 1
        _work_directory(root, packet)
        return _commit(root, head, command_id, request,
            {'transition': deepcopy(transition), 'attempt': deepcopy(attempt),
             'packet': deepcopy(packet), 'budget': budget_status(state)},
            event_type='return_applied', objects={
                f"transitions/{transition['id']}.json": store._canonical(transition),
                f"packets/{packet['id']}.json": store._canonical(packet)})
