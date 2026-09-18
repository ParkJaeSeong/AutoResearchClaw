"""One durable evidence review; no external submission or milestone completion.

Reviewer receives (role, phase, disclosure_packet, frozen_materials, run_dir).
Uncertain host executions require inspection; cached results are republished.
"""
import fcntl
import json
import threading
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from researchclaw.core.research_graph import commands, store
from .service_review_worker import _save

ROLES = ('domain', 'methodology', 'critical')
PHASES = ('initial', 'response', 'final')


def _current(root, work_id):
    state = store.read_head(root)['state']
    work = state.get('execution_work', {}).get(work_id)
    if work is None:
        raise ValueError('execution_work_missing')
    return state, work, work['attempts'][work['current_attempt_id']]


def _fence(root, identity):
    state, work, attempt = _current(root, identity['work_id'])
    if (work['current_attempt_id'] != identity['attempt_id'] or
            work['generation'] != identity['generation'] or
            state.get('work_execution_policy', {}).get('status') in ('stopped', 'completed')):
        raise ValueError('execution_context_changed')
    return attempt


def _apply(root, operation, payload, key):
    # Retry only unrelated HEAD races; handler rechecks generation and policy.
    for _ in range(8):
        try:
            return commands.apply_command(root, operation=operation, payload=payload,
                expected_head=store.read_head(root)['id'], command_id=key)
        except ValueError as exc:
            if str(exc) != 'research_graph_head_conflict':
                raise
    raise ValueError('research_graph_head_conflict')


def _emit(root, identity, kind, role, phase, **extra):
    _fence(root, identity)
    payload = dict(identity, kind=kind, actor=role, payload=dict(phase=phase, **extra))
    key = 'execution:' + store._hash(store._canonical(payload))
    if kind == 'heartbeat':
        key += ':' + uuid4().hex
    return _apply(root, 'execution.record', payload, key)


def _load(path):
    saved = json.loads(path.read_text())
    if store._hash(store._canonical(saved['value'])) != saved['sha256']:
        raise ValueError('execution_saved_result_hash')
    return saved['value']


def _persist(path, value):
    _save(path, dict(value=value, sha256=store._hash(store._canonical(value))))


def _invoke(root, identity, base, role, phase, packet, materials, reviewer):
    run = store._checked_path(base / (phase + '-' + role))
    run.mkdir(exist_ok=True)
    intent = dict(identity, role=role, phase=phase,
        packet_sha256=store._hash(store._canonical(packet)),
        materials_sha256=store._hash(store._canonical(materials)))
    intent_path, result_path = run/'intent.json', run/'result.json'
    if intent_path.exists() and _load(intent_path) != intent:
        raise ValueError('execution_review_binding_changed')
    if result_path.exists():
        if not intent_path.exists():
            raise ValueError('execution_review_intent_missing')
        raw = _load(result_path)
    else:
        if intent_path.exists():
            _emit(root, identity, 'recovery_required', role, phase,
                  reason='review_attempt_requires_inspection')
            raise ValueError('review_attempt_requires_inspection')
        _emit(root, identity, 'role_started', role, phase)
        _persist(intent_path, intent)
        stop = threading.Event()
        errors = []

        def heartbeat():
            while not stop.wait(15):
                try:
                    _emit(root, identity, 'heartbeat', role, phase)
                except (ValueError, OSError) as exc:
                    errors.append(exc)
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            raw = reviewer(role, phase, deepcopy(packet), deepcopy(materials), run)
            # Preserve late output before checking current work applicability.
            _persist(result_path, raw)
        except Exception:
            try:
                _emit(root, identity, 'recovery_required', role, phase,
                      reason='review_attempt_requires_inspection')
            except (ValueError, OSError):
                pass  # Original exception and saved intent remain the recovery evidence.
            raise
        finally:
            stop.set()
            thread.join()
        if errors:
            raise errors[0]
    _fence(root, identity)
    result = raw.get('answer', raw) if isinstance(raw, dict) else raw
    _emit(root, identity, 'role_submitted', role, phase, result=result)
    return result


def run_review(root, work_id, reviewer):
    """Execute or republish the current attempt using only frozen input."""
    root = store._checked_path(Path(root))
    _, work, attempt = _current(root, work_id)
    if work['status'] in ('accepted', 'needs_work', 'blocked', 'waiting_input'):
        return dict(work_id=work_id, status=work['status'])
    identity = dict(work_id=work_id, attempt_id=work['current_attempt_id'], generation=work['generation'])
    _fence(root, identity)
    base = store._checked_path(root/'.execution-runs'/store._hash(store._canonical(identity)))
    base.mkdir(parents=True, exist_ok=True)
    with (base/'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('execution_review_busy') from None
        materials = deepcopy(attempt['input'])
        materials['contract'] = deepcopy(attempt['contract'])
        rounds = {}
        for phase in PHASES:
            packet = dict(disclosed_initials=rounds.get('initial', []) if phase != 'initial' else [],
                          disclosed_responses=rounds.get('response', []) if phase == 'final' else [])
            rounds[phase] = []
            for role in ROLES:
                result = _invoke(root, identity, base, role, phase, packet, materials, reviewer)
                rounds[phase].append(dict(role=role, answer=result))
        packet = dict(disclosed_initials=rounds['initial'], disclosed_responses=rounds['response'],
                      disclosed_finals=rounds['final'])
        result = _invoke(root, identity, base, 'coordinator', 'final', packet, materials, reviewer)
        _fence(root, identity)
        _apply(root, 'execution.finish', dict(identity, result=result),
               'execution-finish:' + store._hash(store._canonical(dict(identity, result=result))))
        _, work, _ = _current(root, work_id)
        return dict(work_id=work_id, status=work['status'])


def resume_review(root, work_id, reviewer):
    return run_review(root, work_id, reviewer)


def main(argv=None):
    import argparse
    from .execution_host import host_reviewer
    parser=argparse.ArgumentParser(description='Run or resume an explicitly prepared evidence review; never complete M1')
    parser.add_argument('root',type=Path)
    parser.add_argument('--work-id',required=True)
    parser.add_argument('--host',required=True,type=Path)
    args=parser.parse_args(argv)
    if not args.host.is_file():parser.error('reviewer host file does not exist')
    result=run_review(args.root,args.work_id,host_reviewer(args.host))
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='accepted' else 2


if __name__=='__main__':
    raise SystemExit(main())
