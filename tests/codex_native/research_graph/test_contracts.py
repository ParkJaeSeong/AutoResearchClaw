"""A01 structural checks; examples are synthetic, not scientific evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from researchclaw.core.research_graph.contracts import validate_record

EXAMPLES = Path(__file__).resolve().parents[3] / 'docs/superpowers/acceptance/research-graph-a01'
KINDS = ('SnapshotRef', 'Issue', 'IssueEvent', 'Verification', 'VerificationResult',
         'Position', 'Decision', 'Handoff', 'Dependency', 'ApprovalBinding')


def example(kind):
    return json.loads((EXAMPLES / f'{kind}.json').read_text())


@pytest.mark.parametrize('kind', KINDS)
def test_complete_examples_valid_and_not_mutated(kind):
    payload = example(kind)
    before = deepcopy(payload)
    assert validate_record(kind, payload) == ()
    assert payload == before


@pytest.mark.parametrize('kind', KINDS)
def test_closed_common_contracts(kind):
    payload = example(kind)
    payload['ready_from_confidence'] = True
    assert any(e['code'] == 'unknown_field' for e in validate_record(kind, payload))
    del payload['ready_from_confidence']
    del payload['producer_id']
    assert any(e['path'] == '$.producer_id' for e in validate_record(kind, payload))


@pytest.mark.parametrize('value', [True, 1.0, '1', 2, None, [], {}])
def test_schema_version_exact_integer(value):
    payload = example('Issue')
    payload['schema_version'] = value
    assert validate_record('Issue', payload)


@pytest.mark.parametrize('field', ['to_milestone', 'owner_assignment_id', 'verification_id', 'acceptance_event_id'])
def test_transfer_acceptance_missing(field):
    payload = example('IssueEvent')
    del payload[field]
    assert any(e['code'] == 'transfer_acceptance_missing' and e['path'] == f'$.{field}'
               for e in validate_record('IssueEvent', payload))


@pytest.mark.parametrize('kind,field', [('Issue', 'severity'), ('Issue', 'category'),
    ('Verification', 'method'), ('VerificationResult', 'outcome'), ('Position', 'stance'),
    ('Position', 'change_kind'), ('Dependency', 'relation'), ('ApprovalBinding', 'validity')])
@pytest.mark.parametrize('bad', ['not-an-enum', [], {}, True])
def test_enums_reject_unknown_and_unhashable(kind, field, bad):
    payload = example(kind)
    payload[field] = bad
    assert validate_record(kind, payload)


@pytest.mark.parametrize('bad', [None, 1, True, '', [], {}, {'project_id': []}])
def test_malformed_nested_reference_never_crashes(bad):
    payload = example('Verification')
    payload['input_refs'] = [bad]
    assert validate_record('Verification', payload)


def test_nested_objects_are_closed_and_hashes_checked():
    payload = example('Issue')
    payload['target_refs'][0]['sha256'] = 'wrong'
    payload['origin']['ready'] = True
    errors = validate_record('Issue', payload)
    assert any(e['path'] == '$.target_refs[0].sha256' for e in errors)
    assert any(e['path'] == '$.origin.ready' for e in errors)


def test_host_observed_requires_observation_reference():
    payload = example('Issue')
    payload['provenance_status'] = 'host_observed'
    assert any(e['code'] == 'observation_refs_missing' for e in validate_record('Issue', payload))
    payload['observation_refs'] = payload['target_refs']
    assert validate_record('Issue', payload) == ()


@pytest.mark.parametrize('bad', [1, 'true', None, [], {}])
def test_ready_requires_exact_bool(bad):
    payload = example('Decision')
    payload['gate_result']['ready'] = bad
    assert validate_record('Decision', payload)


def test_confidence_cannot_replace_or_create_ready():
    position = example('Position')
    position['confidence'] = 90
    assert validate_record('Position', position) == ()
    position['ready'] = True
    assert any(e['code'] == 'unknown_field' for e in validate_record('Position', position))
    decision = example('Decision')
    decision['gate_result'] = {'confidence': 90}
    assert validate_record('Decision', decision)


@pytest.mark.parametrize('kind', [None, [], {}, 'Unknown'])
def test_unknown_kind_returns_error(kind):
    assert validate_record(kind, {})[0]['code'] == 'unknown_kind'


@pytest.mark.parametrize('bad', [None, [], '', True])
def test_non_object_payload_returns_error(bad):
    assert validate_record('Issue', bad)[0]['code'] == 'invalid_type'


def test_structural_success_does_not_resolve_graph_or_validate_transition():
    payload = example('IssueEvent')
    payload['from_status'] = 'resolved'
    payload['to_status'] = 'resolved'
    for field in ('to_milestone', 'owner_assignment_id', 'verification_id', 'acceptance_event_id'):
        del payload[field]
    assert validate_record('IssueEvent', payload) == ()


@pytest.mark.parametrize('kind,field', [('Issue', 'origin'), ('Decision', 'next_action')])
def test_attempt_identity_is_uuid_not_display_ordinal(kind, field):
    payload = example(kind)
    payload[field]['attempt'] = 1
    assert any(e['path'] == f'$.{field}.attempt' for e in validate_record(kind, payload))


def test_issue_can_explicitly_preserve_unassigned_legacy_owner():
    payload = example('Issue')
    payload['owner_assignment_id'] = None
    assert validate_record('Issue', payload) == ()
