"""M1 synthesis structure and exact registered evidence lineage."""
from copy import deepcopy
import importlib
import importlib.util
import json
import subprocess
import sys

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.artifacts import validate_node_contents
from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
from researchclaw.core.m1.packets import prepare_node, register_outputs
from tests.codex_native.m1.helpers import (build_evidence_case, checkpoint, encoded,
    extraction_files, jsonl, submission)


def api():
    name = 'researchclaw.core.m1.synthesis'
    assert importlib.util.find_spec(name) is not None, 'M1 synthesis implementation is missing'
    return importlib.import_module(name)


def record():
    return {'claims': ['C1', 'C2'], 'agreements': [],
            'conflicts': [{'id': 'X1', 'claim_refs': ['C1', 'C2'],
                'interpretations': ['Condition may explain the difference', 'Result may not replicate'],
                'open_questions': ['Which condition differs?']}],
            'gaps': [], 'limitations': ['Evidence does not resolve the conflict']}


def test_conflicting_evidence_and_zero_gaps_are_valid_without_scientific_endorsement():
    value = record()
    before = deepcopy(value)
    assert api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'}) == ()
    status = api().synthesis_status(value)
    assert 'no_verified_gaps' in status['reasons']
    assert status['scientific_validation'] == 'not_performed'
    assert status['hypothesis_possible'] is True
    assert value == before


@pytest.mark.parametrize('section', ['gaps', 'conflicts', 'agreements'])
def test_unknown_claim_references_are_rejected(section):
    value = record()
    item = {'id': 'item', 'question': 'condition?', 'summary': 'agreement',
            'claim_refs': ['missing'], 'interpretations': ['one'], 'open_questions': []}
    value[section] = [item]
    assert any(i['code'] == 'm1_unknown_claim' for i in
               api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'}))


@pytest.mark.parametrize('section', ['gaps', 'conflicts'])
def test_unreferenced_question_requires_explicit_unverified_status_and_reason(section):
    value = record()
    value[section] = [{'id': 'Q1', 'claim_refs': [], 'question': 'condition?',
                      'interpretations': ['one'], 'open_questions': []}]
    assert api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'})
    value[section][0].update(status='unverified_question', reason='No direct evidence collected')
    assert api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'}) == ()
    value[section][0]['status'] = 'verified_gap'
    assert api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'})


@pytest.mark.parametrize('mutation', ['missing_section', 'bad_claim', 'duplicate_id', 'blank_question', 'bad_list'])
def test_malformed_synthesis_is_rejected(mutation):
    value = record()
    if mutation == 'missing_section': del value['limitations']
    elif mutation == 'bad_claim': value['claims'].append('unknown')
    elif mutation == 'duplicate_id': value['conflicts'] *= 2
    elif mutation == 'blank_question': value['gaps'] = [{'id': 'G1', 'question': ' ', 'claim_refs': ['C1']}]
    elif mutation == 'bad_list': value['limitations'] = 'none'
    assert api().validate_synthesis_record(value, known_claim_ids={'C1', 'C2'})


def test_empty_evidence_reports_downstream_reason_without_inventing_gaps():
    value = {key: [] for key in record()}
    assert api().validate_synthesis_record(value, known_claim_ids=set()) == ()
    status = api().synthesis_status(value)
    assert status['hypothesis_possible'] is False
    assert set(status['reasons']) == {'no_claims', 'no_verified_gaps'}
    assert value['gaps'] == []


def test_gap_reference_can_supply_evidence_even_if_claims_summary_is_empty():
    value = {key: [] for key in record()}
    value['gaps'] = [{'id': 'G1', 'question': 'condition?', 'claim_refs': ['C1']}]
    assert api().validate_synthesis_record(value, known_claim_ids={'C1'}) == ()
    assert api().synthesis_status(value)['hypothesis_possible'] is True


def test_node_adapter_checks_refs_against_extraction_snapshot():
    files = {'knowledge/synthesis.json': encoded(record()), 'knowledge/synthesis.md': b'Conflicting evidence'}
    inputs = {'knowledge/extractions.jsonl': jsonl({'claim_id': 'C1'})}
    assert any(i['code'] == 'm1_unknown_claim' for i in
               validate_node_contents({'node_id': 'synthesize'}, files, inputs))


def test_helper_registers_synthesis_with_synthetic_attribution_and_review_gate(tmp_path):
    case = build_evidence_case(tmp_path)
    refs = {ref['logical_path']: ref for ref in case['artifact_refs']}
    assert 'knowledge/synthesis.json' in refs
    head = store.read_head(tmp_path)
    assert head['state']['current_node_id'] == 'synthesize'
    assert head['state']['attempts'][-1]['status'] == 'review_pending'
    assert head['state']['attempts'][-1]['scientific_validation'] == 'not_performed'
    assert refs['knowledge/synthesis.json']['content_origin'] == 'synthetic'
    assert {'root', 'head_id', 'artifact_refs', 'corpus_binding', 'corpus_refs'} <= case.keys()


def test_registration_rejects_bad_synthesis_without_publishing(tmp_path):
    build_evidence_case(tmp_path)
    head = store.read_head(tmp_path)
    head['state']['attempts'] = [a for a in head['state']['attempts'] if a['node_id'] != 'synthesize']
    store.commit_record(tmp_path, expected_head=head['id'], command_id='test-new-attempt',
        state=head['state'], event={**store._VERSION, 'type': 'synthetic_test_checkpoint', 'payload': {}}, objects={})
    packet = prepare_node(tmp_path, 'synthesize', command_id='prepare-bad')['packet']
    before = store.read_head(tmp_path)['state']['artifacts']
    result = register_outputs(tmp_path, packet_id=packet['id'],
        submission=submission(tmp_path, packet, {'knowledge/synthesis.json': encoded(record()),
                                               'knowledge/synthesis.md': b'unknown claims'}), command_id='register-bad')
    assert result['status'] == 'draft_invalid'
    assert any(i['code'] == 'm1_unknown_claim' for i in result['issues'])
    assert store.read_head(tmp_path)['state']['artifacts'] == before


def test_trace_follows_registered_extraction_corpus_approval_and_abstract_locator(tmp_path):
    case = build_evidence_case(tmp_path)
    before = (tmp_path / '.researchclaw/m1/HEAD.json').read_bytes()
    trace = api().trace_claim(api().read_trace_head(tmp_path), 'claim-one')
    assert trace['claim']['claim_id'] == 'claim-one'
    assert trace['source']['source_id'] == 'src-one'
    assert trace['corpus']['corpus_binding'] == case['corpus_binding']
    assert trace['approval_at_extraction']['decision'] == 'approve'
    assert trace['current_authorization']['approved'] is True
    assert trace['original']['locator'] == 'Abstract'
    assert trace['original']['url'] == 'https://example.org/synthetic'
    assert trace['original']['access_level'] == 'abstract'
    assert trace['original']['full_text_verified'] is False
    assert trace['original']['file_available'] is False
    assert trace['limitations'] == ['Full text was not accessed']
    assert trace['content_origin'] == 'synthetic'
    assert (tmp_path / '.researchclaw/m1/HEAD.json').read_bytes() == before


def test_trace_pins_old_extraction_despite_newer_claim_bytes_draft_and_revocation(tmp_path):
    case = build_evidence_case(tmp_path)
    original = api().read_trace_head(tmp_path)
    original_ref = original['trace_synthesis_ref']['id']
    files = extraction_files(original['state']['project_id'])
    claim = json.loads(files['knowledge/extractions.jsonl'])
    claim['claim'] = 'new incompatible assertion'
    packet = next(p for p in original['state']['packets'].values() if p['node_id'] == 'extract')
    (tmp_path / packet['work_dir'] / 'knowledge/extractions.jsonl').write_bytes(jsonl(claim))
    checkpoint(tmp_path, files={'knowledge/extractions.jsonl': jsonl(claim)})
    record_corpus_approval(tmp_path, corpus_binding=case['corpus_binding'], decision='reject',
        note='synthetic revocation', command_id='reject-later')
    trace = api().trace_claim(api().read_trace_head(tmp_path, synthesis_ref_id=original_ref), 'claim-one')
    assert trace['claim']['claim'] != 'new incompatible assertion'
    assert trace['approval_at_extraction']['decision'] == 'approve'
    assert trace['current_authorization']['approved'] is False
    assert trace['current_authorization']['approval']['decision'] == 'reject'
    assert api().trace_claim(original, 'claim-one')['current_authorization']['approved'] is True


def test_trace_missing_context_unknown_claim_and_damaged_bytes_fail_explicitly(tmp_path):
    build_evidence_case(tmp_path)
    with pytest.raises(ValueError, match='m1_trace_context_missing'):
        api().trace_claim(store.read_head(tmp_path), 'claim-one')
    head = api().read_trace_head(tmp_path)
    with pytest.raises(ValueError, match='m1_unknown_claim'):
        api().trace_claim(head, 'missing')
    extraction = next(ref for ref in head['state']['artifacts'] if ref['logical_path'] == 'knowledge/extractions.jsonl')
    head['trace_object_bytes'][extraction['sha256']] = b'changed'
    with pytest.raises(ValueError, match='m1_input_content_changed'):
        api().trace_claim(head, 'claim-one')


def test_new_corpus_approval_does_not_authorize_old_trace(tmp_path):
    case = build_evidence_case(tmp_path)
    head = store.read_head(tmp_path)
    ref = next(ref for ref in head['state']['artifacts'] if ref['logical_path'] == 'scope/goal.md')
    checkpoint(tmp_path, files={'scope/goal.md': store._read_file(store._store_path(tmp_path) / 'objects' / ref['sha256'])})
    corpus = current_corpus(tmp_path)
    assert corpus['corpus_binding'] != case['corpus_binding']
    record_corpus_approval(tmp_path, corpus_binding=corpus['corpus_binding'], decision='approve',
        note='new synthetic corpus', command_id='approve-new-corpus')
    trace = api().trace_claim(api().read_trace_head(tmp_path), 'claim-one')
    assert trace['approval_at_extraction']['corpus_binding'] == case['corpus_binding']
    assert trace['current_authorization']['approved'] is False
    assert trace['current_authorization']['traced_corpus_is_current'] is False


@pytest.mark.parametrize('missing', ['bytes', 'producer', 'registration', 'approval'])
def test_missing_exact_lineage_never_falls_back_to_current_state(tmp_path, missing):
    build_evidence_case(tmp_path)
    head = api().read_trace_head(tmp_path)
    ref = next(ref for ref in head['state']['artifacts'] if ref['logical_path'] == 'knowledge/extractions.jsonl')
    if missing == 'bytes':
        del head['trace_object_bytes'][ref['sha256']]
        error = 'm1_trace_object_missing'
    elif missing == 'producer':
        head['state']['attempts'] = [a for a in head['state']['attempts'] if a['id'] != ref['producer_attempt_id']]
        error = 'm1_trace_producer_missing'
    elif missing == 'registration':
        head['events'] = [e for e in head['events'] if e['type'] != 'node_outputs_registered']
        error = 'm1_trace_registration_missing'
    else:
        head['events'] = [e for e in head['events'] if e['type'] != 'corpus_decided']
        error = 'm1_trace_approval_missing'
    with pytest.raises(ValueError, match=error):
        api().trace_claim(head, 'claim-one')


def test_trace_preserves_conflicts_and_can_select_an_older_synthesis(tmp_path):
    build_evidence_case(tmp_path)
    old = api().read_trace_head(tmp_path)
    old_ref = old['trace_synthesis_ref']['id']
    head = store.read_head(tmp_path)
    # A declared synthetic new attempt, preserving the earlier producer record.
    prior = next(a for a in head['state']['attempts'] if a['node_id'] == 'synthesize')
    newer = deepcopy(prior)
    newer.update(id='fixture-synthesis-v2', output_refs=[], status='prepared', validation_history=[])
    packet = deepcopy(head['state']['packets'][prior['packet_id']])
    packet.update(id='fixture-packet-v2', attempt_id=newer['id'], work_dir='m1/work/fixture-synthesis-v2')
    newer['packet_id'] = packet['id']
    head['state']['attempts'].append(newer)
    head['state']['packets'][packet['id']] = packet
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture-v2', state=head['state'],
        event={**store._VERSION, 'type': 'synthetic_test_checkpoint', 'payload': {'provenance_status': 'declared_only'}}, objects={})
    value = {'claims': ['claim-one'], 'agreements': [], 'gaps': [], 'limitations': ['unresolved'],
        'conflicts': [{'id': 'X1', 'claim_refs': ['claim-one'], 'interpretations': ['one', 'another'],
                       'open_questions': ['which interpretation?']}]}
    register_outputs(tmp_path, packet_id=packet['id'], submission=submission(tmp_path, packet,
        {'knowledge/synthesis.json': encoded(value), 'knowledge/synthesis.md': b'Unresolved interpretations'}), command_id='register-v2')
    trace = api().trace_claim(api().read_trace_head(tmp_path), 'claim-one')
    assert trace['conflicts'][0]['interpretations'] == ['one', 'another']
    assert api().trace_claim(api().read_trace_head(tmp_path, synthesis_ref_id=old_ref), 'claim-one')['conflicts'] == []
    with pytest.raises(ValueError, match='m1_trace_synthesis_missing'):
        api().read_trace_head(tmp_path, synthesis_ref_id='missing')


def test_trace_cli_emits_one_json_value_and_stderr_only_errors(tmp_path):
    build_evidence_case(tmp_path)
    command = [sys.executable, '-m', 'researchclaw.codex.cli', 'm1', 'trace', str(tmp_path), '--json', '--claim']
    result = subprocess.run(command + ['claim-one'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['claim']['claim_id'] == 'claim-one'
    assert result.stderr == ''
    invalid = subprocess.run(command + ['missing'], text=True, capture_output=True)
    assert invalid.returncode == 2
    assert invalid.stdout == ''
    assert 'm1_unknown_claim' in invalid.stderr
