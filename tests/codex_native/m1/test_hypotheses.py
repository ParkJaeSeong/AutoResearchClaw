"""Hypothesis behavior; all checkpoint progression is synthetic, declared_only."""
from copy import deepcopy
import importlib
import importlib.util
import json
from uuid import uuid4

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.artifacts import validate_node_contents
from researchclaw.core.m1.packets import prepare_node, register_outputs
from tests.codex_native.m1.helpers import build_evidence_case, checkpoint, encoded, jsonl, submission


PATH = 'hypotheses/hypotheses.json'


def api():
    name = 'researchclaw.core.m1.hypotheses'
    assert importlib.util.find_spec(name) is not None, 'M1 hypothesis implementation is missing'
    return importlib.import_module(name)


def candidate(**updates):
    value = {'id': 'H1', 'revision': 1, 'parent_revision': None,
             'author_assignment_id': 'author-one', 'change_reason': None,
             'statement': 'The observed difference depends on context.',
             'claim_refs': ['claim-one'], 'gap_refs': [],
             'predicted_observation': 'The difference diminishes in a shared context.',
             'falsification_condition': 'The difference persists under comparable conditions.',
             'alternatives': ['Selection effects explain the observed difference.'],
             'feasibility_notes': 'Comparable observations appear accessible; access is unverified.',
             'open_design_questions': ['Which conditions and measurements should M2 use?'],
             'disposition': 'draft'}
    return {**value, **updates}


def envelope(*records, **updates):
    return {'schema_version': 1, 'hypotheses': list(records), **updates}


def files(value):
    return {PATH: encoded(value), 'hypotheses/hypotheses.md': b'Synthetic hypothesis; unreviewed.'}


def inputs(*, previous=None):
    value = {'knowledge/extractions.jsonl': jsonl({'claim_id': 'claim-one'}),
             'knowledge/synthesis.json': encoded({'claims': [], 'agreements': [], 'conflicts': [],
                 'gaps': [{'id': 'G1', 'question': 'Which context?', 'claim_refs': ['claim-one']}],
                 'limitations': []})}
    if previous is not None:
        value[PATH] = encoded(previous)
    return value


def validate(value, bound=None):
    return validate_node_contents({'node_id': 'hypothesize'}, files(value), bound or inputs())


def test_single_qualitative_candidate_with_no_gap_or_numeric_magnitude_is_valid():
    value = candidate()
    before = deepcopy(value)
    assert api().validate_hypothesis(value, claim_ids={'claim-one'}, gap_ids=set()) == ()
    assert validate(envelope(value)) == ()
    assert value == before


def test_revision_identity_and_author_separation():
    assert api().hypothesis_key({'id': 'H1', 'revision': 2}) == ('H1', 2)
    assert not api().can_review(author_assignment_id='A1', reviewer_assignment_id='A1')
    assert api().can_review(author_assignment_id='A1', reviewer_assignment_id='A2')


@pytest.mark.parametrize('updates', [
    {'id': ''}, {'revision': True}, {'revision': 0}, {'revision': 1.5},
    {'parent_revision': 0}, {'revision': 2, 'parent_revision': None},
    {'revision': 3, 'parent_revision': 1, 'change_reason': 'revised'},
    {'author_assignment_id': ' '}, {'statement': None}, {'falsification_condition': ''},
    {'alternatives': 'none'}, {'open_design_questions': [None]}, {'feasibility_notes': ''},
    {'disposition': 'proven'}, {'claim_refs': ['claim-one', 'claim-one']},
    {'gap_refs': {}}, {'claim_refs': [], 'gap_refs': []},
])
def test_malformed_or_unfalsifiable_candidate_is_rejected(updates):
    assert api().validate_hypothesis(candidate(**updates), claim_ids={'claim-one'}, gap_ids={'G1'})


@pytest.mark.parametrize('field,reference,code', [
    ('claim_refs', 'unknown', 'm1_unknown_claim'), ('gap_refs', 'unknown', 'm1_unknown_gap')])
def test_unknown_reference_reports_its_kind(field, reference, code):
    assert any(issue['code'] == code for issue in validate(envelope(candidate(**{field: [reference]}))))


def test_gap_only_candidate_can_reference_exact_synthesis_gap():
    assert validate(envelope(candidate(claim_refs=[], gap_refs=['G1']))) == ()


def test_no_candidate_outcome_requires_a_reason_and_does_not_fabricate_one():
    assert validate(envelope())
    assert validate(envelope(no_hypotheses_reason='Evidence cannot support a testable proposal.')) == ()


@pytest.mark.parametrize('value', [[], {}, {'schema_version': True, 'hypotheses': []},
                                   envelope(candidate(), candidate())])
def test_invalid_envelope_or_duplicate_revision_is_rejected(value):
    assert validate(value)


def test_new_revision_requires_registered_parent_and_explicit_change_reason():
    old = candidate()
    revised = candidate(revision=2, parent_revision=1, change_reason='Critique identified a confounder.',
                        statement='The difference depends on comparable exposure.')
    assert validate(envelope(old, revised))  # A copied parent in a draft is not registered history.
    assert validate(envelope(old, revised), inputs(previous=envelope(old))) == ()
    for reason in (None, '', ' '):
        revised['change_reason'] = reason
        assert validate(envelope(old, revised), inputs(previous=envelope(old)))


@pytest.mark.parametrize('mutation', ['overwrite', 'omit', 'author', 'skip'])
def test_registered_history_cannot_be_overwritten_omitted_or_reparented(mutation):
    old = candidate()
    revised = candidate(revision=2, parent_revision=1, change_reason='Narrowed after critique.')
    value = envelope(old, revised)
    if mutation == 'overwrite': value['hypotheses'][0] = candidate(statement='Overwritten old statement')
    elif mutation == 'omit': value['hypotheses'] = [revised]
    elif mutation == 'author': revised['author_assignment_id'] = 'different-author'
    elif mutation == 'skip': revised.update(revision=3, parent_revision=2)
    assert validate(value, inputs(previous=envelope(candidate())))


def prepare_case(root):
    build_evidence_case(root)
    checkpoint(root, node='hypothesize')
    return prepare_node(root, 'hypothesize', command_id='hypothesis-prepare')['packet']


def next_attempt(root):
    """Inject a new draft packet, preserving every prior attempt and artifact."""
    head = store.read_head(root)
    prior = head['state']['attempts'][-1]
    packet = deepcopy(head['state']['packets'][prior['packet_id']])
    attempt_id, packet_id = 'synthetic-' + uuid4().hex, 'synthetic-' + uuid4().hex
    refs = packet['inputs']['objects']
    refs.append(next(ref for ref in prior['output_refs'] if ref['logical_path'] == PATH))
    refs.sort(key=lambda ref: (ref['id'], ref['sha256']))
    packet.update(id=packet_id, attempt_id=attempt_id, work_dir=f'm1/work/{attempt_id}')
    packet['input_binding'] = store._hash(store._canonical({
        'packet_version': 1, 'objects': [{'id': ref['id'], 'sha256': ref['sha256']} for ref in refs],
        'configuration': packet['inputs']['configuration']}))
    value = {**deepcopy(prior), 'id': attempt_id, 'packet_id': packet_id,
             'revision': prior['revision'] + 1, 'parent_attempt_id': prior['id'],
             'input_refs': deepcopy(refs), 'status': 'prepared', 'output_refs': [],
             'validation_history': [], 'structural_validation': 'not_performed'}
    head['state']['attempts'].append(value)
    head['state']['packets'][packet_id] = packet
    store.commit_record(root, expected_head=head['id'], command_id='synthetic-' + uuid4().hex,
        state=head['state'], event={**store._VERSION, 'type': 'synthetic_test_checkpoint',
            'payload': {'provenance_status': 'declared_only', 'note': 'No real review or graph advancement'}}, objects={})
    return prepare_node(root, 'hypothesize', command_id='prepare-' + uuid4().hex)['packet']


def register(root, packet, value):
    return register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files(value)),
                            command_id='register-' + uuid4().hex)


def test_registration_rejects_unknown_evidence_without_publishing(tmp_path):
    packet = prepare_case(tmp_path)
    before = store.read_head(tmp_path)['state']['artifacts']
    result = register(tmp_path, packet, envelope(candidate(claim_refs=['unknown'])))
    assert result['status'] == 'draft_invalid'
    assert any(issue['code'] == 'm1_unknown_claim' for issue in result['issues'])
    assert store.read_head(tmp_path)['state']['artifacts'] == before


def test_registration_binds_selected_synthesis_extraction_not_latest_or_mutable_draft(tmp_path):
    packet = prepare_case(tmp_path)
    selected_refs = [ref for ref in packet['inputs']['objects'] if ref['logical_path'] == 'knowledge/extractions.jsonl']
    assert len(selected_refs) == 1
    selected = selected_refs[0]
    head = store.read_head(tmp_path)
    original = next(ref for ref in head['state']['artifacts'] if ref['logical_path'] == 'knowledge/extractions.jsonl')
    assert selected == original
    checkpoint(tmp_path, files={'knowledge/extractions.jsonl': jsonl({'claim_id': 'new-claim'})})
    result = register(tmp_path, packet, envelope(candidate()))
    assert result['status'] == 'review_pending'
    assert store.read_head(tmp_path)['state']['attempts'][-1]['scientific_validation'] == 'not_performed'


def test_registered_revisions_preserve_old_bytes_author_and_change_reason(tmp_path):
    packet = prepare_case(tmp_path)
    old = candidate()
    first = register(tmp_path, packet, envelope(old))
    assert first['status'] == 'review_pending'
    old_ref = next(ref for ref in first['artifacts'] if ref['logical_path'] == PATH)
    later = next_attempt(tmp_path)
    assert old_ref in later['inputs']['objects']
    revised = candidate(revision=2, parent_revision=1, change_reason='Critique exposed a confounder.',
                        falsification_condition='The difference persists after matching exposure.')
    result = register(tmp_path, later, envelope(old, revised))
    assert result['status'] == 'review_pending', result
    assert json.loads(store._read_file(store._store_path(tmp_path) / 'objects' / old_ref['sha256'])) == envelope(old)
    latest_ref = next(ref for ref in result['artifacts'] if ref['logical_path'] == PATH)
    assert latest_ref['sha256'] != old_ref['sha256']


def test_first_authoring_packet_pins_old_extraction_when_a_newer_version_already_exists(tmp_path):
    build_evidence_case(tmp_path)
    head = store.read_head(tmp_path)
    original = next(ref for ref in head['state']['artifacts'] if ref['logical_path'] == 'knowledge/extractions.jsonl')
    checkpoint(tmp_path, node='hypothesize', files={'knowledge/extractions.jsonl': jsonl({'claim_id': 'new-claim'})})
    packet = prepare_node(tmp_path, 'hypothesize', command_id='prepare')['packet']
    assert original in packet['inputs']['objects']
    result = register(tmp_path, packet, envelope(candidate(claim_refs=['new-claim'])))
    assert result['status'] == 'draft_invalid'
    assert any(issue['code'] == 'm1_unknown_claim' for issue in result['issues'])


@pytest.mark.parametrize('missing', ['producer', 'extraction'])
def test_missing_exact_synthesis_lineage_never_falls_back_to_latest_extraction(tmp_path, missing):
    build_evidence_case(tmp_path)
    head = store.read_head(tmp_path)
    synthesis = head['state']['attempts'][-1]
    if missing == 'producer': synthesis['node_id'] = 'extract'
    else: synthesis['input_refs'] = []
    head['state']['current_node_id'] = 'hypothesize'
    store.commit_record(tmp_path, expected_head=head['id'], command_id='missing-lineage', state=head['state'],
        event={**store._VERSION, 'type': 'synthetic_test_checkpoint',
               'payload': {'provenance_status': 'declared_only'}}, objects={})
    with pytest.raises(ValueError, match='m1_hypothesis_.*missing'):
        prepare_node(tmp_path, 'hypothesize', command_id='prepare')


def test_old_revisions_are_preserved_without_reinterpreting_their_old_references():
    old = candidate()
    revised = candidate(revision=2, parent_revision=1, change_reason='New evidence changed the interpretation.',
                        claim_refs=['claim-new'], statement='A narrower account fits new evidence.')
    bound = inputs(previous=envelope(old))
    bound['knowledge/extractions.jsonl'] = jsonl({'claim_id': 'claim-new'})
    bound['knowledge/synthesis.json'] = encoded({'claims': ['claim-new'], 'agreements': [],
        'conflicts': [], 'gaps': [], 'limitations': []})
    assert validate(envelope(old, revised), bound) == ()
    revised['claim_refs'] = ['claim-one']
    assert any(issue['code'] == 'm1_unknown_claim' for issue in validate(envelope(old, revised), bound))


def test_registration_of_a_changed_revision_without_reason_preserves_history(tmp_path):
    first_packet = prepare_case(tmp_path)
    old = candidate()
    assert register(tmp_path, first_packet, envelope(old))['status'] == 'review_pending'
    packet = next_attempt(tmp_path)
    before = store.read_head(tmp_path)['state']['artifacts']
    result = register(tmp_path, packet, envelope(old, candidate(revision=2, parent_revision=1,
        statement='A changed claim with no recorded reason.')))
    assert result['status'] == 'draft_invalid'
    assert any(issue.get('path') == 'change_reason' for issue in result['issues'])
    assert store.read_head(tmp_path)['state']['artifacts'] == before


def test_mutable_extraction_draft_cannot_supply_a_new_hypothesis_reference(tmp_path):
    packet = prepare_case(tmp_path)
    head = store.read_head(tmp_path)
    extraction = next(p for p in head['state']['packets'].values() if p['node_id'] == 'extract')
    (tmp_path / extraction['work_dir'] / 'knowledge/extractions.jsonl').write_bytes(jsonl({'claim_id': 'draft-claim'}))
    result = register(tmp_path, packet, envelope(candidate(claim_refs=['draft-claim'])))
    assert result['status'] == 'draft_invalid'
    assert any(issue['code'] == 'm1_unknown_claim' for issue in result['issues'])
