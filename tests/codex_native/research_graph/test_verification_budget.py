from copy import deepcopy
import pytest
from researchclaw.core.research_graph import commands, store
from .test_verification import Fixture, envelope, uid


def budget(f):
    return {**envelope(f.project), 'owner_assignment_id': f.owner['id'],
            'scope': 'Check the corrected selection only',
            'resource_limits': ['Existing session resources; no experiments'],
            'input_refs': [f.input_ref]}


def test_budget_public_registration_and_verification(tmp_path):
    f = Fixture(tmp_path / 'project')
    b = budget(f)
    before = deepcopy(f.head['state'])
    h = f.apply('verification.budget.register', {'budget': b})
    assert h['state']['verification_budgets'][b['id']] == b
    assert h['state'].get('issue_states') == before.get('issue_states')
    assert h['state'].get('approval_receipts') == before.get('approval_receipts')
    ref = dict(project_id=f.project, head_id=h['id'], artifact_id='verification-budgets/' + b['id'],
               sha256=store._hash(store._canonical(b)))
    _, result = f.prepare(f.verification(budget_ref=ref))
    assert result['state']['verifications']


@pytest.mark.parametrize('change', ['wrong_owner', 'empty_limits', 'unknown_field', 'bad_ref'])
def test_invalid_budget_preserves_head(tmp_path, change):
    f = Fixture(tmp_path / 'project'); b = budget(f); before = f.head['id']
    if change == 'wrong_owner': b['owner_assignment_id'] = f.resolver['id']
    if change == 'empty_limits': b['resource_limits'] = []
    if change == 'unknown_field': b['approved'] = True
    if change == 'bad_ref': b['input_refs'][0] = {**f.input_ref, 'sha256': '0' * 64}
    with pytest.raises(ValueError): f.apply('verification.budget.register', {'budget': b})
    assert store.read_head(f.root)['id'] == before
