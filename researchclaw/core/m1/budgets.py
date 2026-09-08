"""Explicit return ceilings; no automatic budget increases or research approval."""
from copy import deepcopy
from pathlib import Path

from . import store
from .packets import _commit, _mutation, _replay, _request


def can_start_return(*, used: int, limit: int) -> bool:
    if type(used) is not int or type(limit) is not int or used < 0 or limit < 0:
        raise ValueError('m1_budget_invalid')
    return used < limit


def budget_status(state: dict) -> dict:
    available = can_start_return(used=state['returns_used'], limit=state['max_returns'])
    return {'max_returns': state['max_returns'], 'returns_used': state['returns_used'],
            'remaining': max(0, state['max_returns'] - state['returns_used']), 'exhausted': not available}


def set_return_budget(root: Path, *, limit: int, note: str, command_id: str) -> dict:
    """Record the caller's explicit user instruction, declared rather than authenticated."""
    request = _request(command_id, {'operation': 'set_return_budget', 'limit': limit, 'note': note})
    with _mutation(root) as root:
        replay = _replay(root, command_id, request)
        if replay is not None:
            return replay
        can_start_return(used=0, limit=limit)
        if not isinstance(note, str) or not note.strip():
            raise ValueError('m1_budget_invalid')
        head = store.read_head(root)
        state = head['state']
        budget_status(state)
        change = {**store._VERSION, 'previous_limit': state['max_returns'], 'limit': limit,
                  'returns_used': state['returns_used'], 'note': note,
                  'authority': 'explicit_user_declaration', 'provenance_status': 'declared_only'}
        state['max_returns'] = limit
        state.setdefault('budget_changes', []).append(change)
        return _commit(root, head, command_id, request,
                       {'budget': budget_status(state), 'change': deepcopy(change)},
                       event_type='return_budget_set', objects={})
