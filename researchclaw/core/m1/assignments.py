"""Declared reviewer assignment contracts; strings never authenticate a host."""
from copy import deepcopy

from . import store

JUDGING_ROLES = ('domain', 'methodology', 'critical_reproducibility')
ASSIGNMENT_INPUT_FIELDS = {'id', 'role_id', 'host_task_id'}


def bind_assignments(assignments: list[dict], *, session_id: str, input_binding: str,
                     author_assignment_ids: set[str], author_host_task_ids: set[str] | None = None) -> list[dict]:
    """Validate exactly three distinct declared reviewers and bind their scope."""
    if (type(assignments) is not list or len(assignments) != 3
            or not store._is_digest(input_binding) or not isinstance(session_id, str) or not session_id.strip()):
        raise ValueError('m1_assignment_invalid')
    for value in assignments:
        if (type(value) is not dict or set(value) != ASSIGNMENT_INPUT_FIELDS
                or any(not isinstance(value[key], str) or not value[key].strip() for key in value)):
            raise ValueError('m1_assignment_invalid')
    if ({a['role_id'] for a in assignments} != set(JUDGING_ROLES)
            or len({a['id'] for a in assignments}) != 3
            or len({a['host_task_id'] for a in assignments}) != 3):
        raise ValueError('m1_assignment_not_independent')
    if any(a['id'] in author_assignment_ids or a['host_task_id'] in (author_host_task_ids or set())
           for a in assignments):
        raise ValueError('m1_assignment_self_review')
    return [{**deepcopy(a), 'session_id': session_id, 'input_binding': input_binding,
             'allowed_outputs': ['initial'], 'provenance_status': 'declared_only'}
            for a in sorted(assignments, key=lambda a: a['id'])]
