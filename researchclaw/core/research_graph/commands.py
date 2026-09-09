"""Explicit pure-operation registry; the sole public mutation dispatcher.

Handlers receive a verified receipt and frozen payload and return state_patch,
event, object_inputs. No dynamic imports or arbitrary patch operation is exposed.
"""
import json
from pathlib import Path
from ..transactions import project_transaction
from . import store
from .issues import propose_issue_event
from .verification import prepare_verification, register_verification_result

_HANDLERS = {'issue.event': propose_issue_event,
             'verification.prepare': prepare_verification,
             'verification.result': register_verification_result}


def _hydrate_policy_snapshot(base, history):
    """Attach verified ancestry and bytes for pure policy validation."""
    snapshot = json.loads(store._canonical(store._receipt(*history[-1])))
    snapshot['_issue_context'] = {
        'history': json.loads(store._canonical([[head, record] for head, record in history])),
        'objects': {digest: store._read_file(base / 'objects' / digest)
                    for digest in snapshot['objects']},
    }
    return snapshot


def read_policy_snapshot(root: Path) -> dict:
    """Read one verified HEAD with the private context required by pure policies."""
    base = store._store_path(root)
    if not base.exists():
        raise ValueError('research_graph_project_not_found')
    history = store._history(base)
    return _hydrate_policy_snapshot(base, history)


def register_operation(operation, handler):
    if not isinstance(operation, str) or not operation.strip() or not callable(handler) or operation in _HANDLERS:
        raise ValueError('research_graph_operation_invalid')
    _HANDLERS[operation] = handler


def apply_command(root: Path, *, operation: str, payload: dict, expected_head: str, command_id: str) -> dict:
    if type(operation) is not str or operation not in _HANDLERS:
        raise ValueError('unknown_operation')
    if type(payload) is not dict or not store._is_digest(expected_head) or not isinstance(command_id, str) or not command_id.strip():
        raise ValueError('research_graph_record_invalid')
    payload = json.loads(store._canonical(payload))
    fingerprint = store._hash(store._canonical({'operation': operation, 'payload': payload}))
    base = store._store_path(root)
    store._history(base)
    store._checked_path(base.parent / 'project-transaction.lock')
    with project_transaction(base.parent.parent):
        history = store._history(base)
        for cid, record in history:
            if record['command_id'] == command_id:
                if record['events'][-1]['payload'].get('_command_request') != fingerprint:
                    raise ValueError('research_graph_command_conflict')
                store._sync_publication(base)
                return store._receipt(cid, record)
        snapshot = store._receipt(*history[-1])
        if snapshot['id'] != expected_head:
            raise ValueError('research_graph_head_conflict')
        # A handler cannot mutate the original snapshot used for the patch.
        handler_snapshot = json.loads(store._canonical(snapshot))
        if operation in ('issue.event', 'verification.prepare', 'verification.result'):
            handler_snapshot = _hydrate_policy_snapshot(base, history)
        plan = _HANDLERS[operation](handler_snapshot, payload)
        event = json.loads(store._canonical(plan['event']))
        event['payload']['_command_request'] = fingerprint
        return store.commit_record(root, expected_head=expected_head, command_id=command_id,
            state={**snapshot['state'], **plan['state_patch']}, event=event, objects=plan['object_inputs'])


def init_project(root: Path, *, topic: str, content_origin: str, max_returns: int = 3,
                 max_verification_runs: int = 10) -> dict:
    """Create an empty research project; counters are not execution permission."""
    from uuid import uuid4
    if (not isinstance(topic, str) or not topic.strip()
            or content_origin not in ('real', 'synthetic', 'mixed')
            or type(max_returns) is not int or max_returns < 0
            or type(max_verification_runs) is not int or max_verification_runs < 0):
        raise ValueError('research_graph_project_config_invalid')
    config = dict(topic=topic, content_origin=content_origin, max_returns=max_returns,
                  max_verification_runs=max_verification_runs)
    store._canonical(config)
    root = store._checked_path(root)
    base = store._store_path(root)
    if not base.exists():
        store._check_new_root(root)
    else:
        store._history(base)
    store._mkdir_durable(root)
    store._mkdir_durable(base.parent)
    store._checked_path(base.parent / 'project-transaction.lock')
    with project_transaction(root):
        if base.exists():
            history = store._history(base)
            original = history[0][1]
            if original['command_id'] != 'init' or original['events'][0] != {**store._VERSION, 'type': 'project_initialized', 'payload': config}:
                raise ValueError('research_graph_project_config_conflict')
            store._sync_publication(base)
            return store._receipt(*history[0])
        return store.initialize_record(root, command_id='init',
            state={**store._VERSION, **config, 'project_id': str(uuid4()),
                   'returns_used': 0, 'verification_runs_used': 0,
                   'execution_cost_limit': None, 'observed_cost': None, 'cost_status': 'unknown'},
            event={**store._VERSION, 'type': 'project_initialized', 'payload': config}, objects={})
