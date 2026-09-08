"""Declared assignment checks cannot authenticate native host execution."""
from copy import deepcopy
import importlib
import importlib.util

import pytest


def api():
    name = 'researchclaw.core.m1.assignments'
    assert importlib.util.find_spec(name) is not None, 'M1 assignment validation is missing'
    return importlib.import_module(name)


def assignments():
    return [{'id': 'A' + str(i), 'role_id': role, 'host_task_id': 'host-' + str(i)}
            for i, role in enumerate(('domain', 'methodology', 'critical_reproducibility'), 1)]


def test_assignment_binding_is_shared_and_provenance_is_only_declared():
    values = assignments()
    before = deepcopy(values)
    result = api().bind_assignments(values, session_id='S1', input_binding='a' * 64,
                                    author_assignment_ids={'author-one'})
    assert values == before
    assert len(result) == 3
    assert all(a['session_id'] == 'S1' and a['input_binding'] == 'a' * 64 for a in result)
    assert all(a['provenance_status'] == 'declared_only' for a in result)
    assert all(a['allowed_outputs'] == ['initial'] for a in result)


@pytest.mark.parametrize('case', ['missing', 'role', 'id', 'host', 'author', 'empty', 'attestation'])
def test_invalid_or_self_review_assignment_rejected(case):
    values = assignments()
    if case == 'missing': values.pop()
    if case == 'role': values[1]['role_id'] = 'domain'
    if case == 'id': values[1]['id'] = 'A1'
    if case == 'host': values[1]['host_task_id'] = 'host-1'
    if case == 'author': values[1]['id'] = 'author-one'
    if case == 'empty': values[1]['host_task_id'] = ' '
    if case == 'attestation': values[1]['provenance_status'] = 'host_verified'
    with pytest.raises(ValueError, match='m1_assignment'):
        api().bind_assignments(values, session_id='S1', input_binding='a' * 64,
                               author_assignment_ids={'author-one'})
