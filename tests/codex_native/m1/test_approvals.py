import importlib.util
import json
import subprocess
import sys

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.packets import prepare_node, register_outputs
from researchclaw.core.m1.project import resume_project
from tests.codex_native.m1.helpers import (build_evidence_case, checkpoint, corpus_checkpoint,
    corpus_files, extraction_files, submission)
from tests.codex_native.m1.test_project import snapshot


def api():
    assert importlib.util.find_spec('researchclaw.core.m1.approvals') is not None, 'corpus approvals are missing'
    from researchclaw.core.m1 import approvals
    return approvals


def fixture(root):
    api()
    return corpus_checkpoint(root)


def decide(root, binding, decision='approve', command='decision'):
    return api().record_corpus_approval(root, corpus_binding=binding, decision=decision,
                                      note='합성 검사 자료: explicit test decision', command_id=command)


def test_old_approval_does_not_cover_changed_corpus():
    covers = api().approval_covers
    record = {'decision': 'approve', 'corpus_binding': 'a' * 64}
    assert covers(record, 'a' * 64)
    assert not covers(record, 'b' * 64)
    assert not covers({'decision': 'reject', 'corpus_binding': 'a' * 64}, 'a' * 64)


def test_decision_is_durable_idempotent_and_does_not_advance_council(tmp_path):
    case = fixture(tmp_path)
    result = decide(tmp_path, case['corpus_binding'])
    assert result['approval']['actor'] == 'user'
    assert result['approval']['provenance_status'] == 'declared_only'
    assert result['receipt']['state']['current_node_id'] == 'screen'
    assert resume_project(tmp_path)['action'] == 'await_review'
    assert decide(tmp_path, case['corpus_binding']) == result
    with pytest.raises(ValueError, match='m1_command_conflict'):
        decide(tmp_path, case['corpus_binding'], 'reject')
    assert len(store.read_head(tmp_path)['state']['approvals']) == 1


def test_unapproved_and_revoked_extraction_remain_blocked_on_resume_and_register(tmp_path):
    case = fixture(tmp_path)
    checkpoint(tmp_path, node='extract')
    with pytest.raises(ValueError, match='m1_corpus_approval_required'):
        prepare_node(tmp_path, 'extract', command_id='unapproved')
    assert resume_project(tmp_path)['action'] == 'await_approval'
    approved = decide(tmp_path, case['corpus_binding'])
    packet = prepare_node(tmp_path, 'extract', command_id='prepared')['packet']
    files = extraction_files(store.read_head(tmp_path)['state']['project_id'])
    manifest = submission(tmp_path, packet, files)
    rejected = decide(tmp_path, case['corpus_binding'], 'reject', 'reject')
    before = snapshot(tmp_path)
    assert resume_project(tmp_path)['action'] == 'await_approval'
    assert snapshot(tmp_path) == before
    for call in [lambda: prepare_node(tmp_path, 'extract', command_id='new-prepare'),
                 lambda: register_outputs(tmp_path, packet_id=packet['id'], submission=manifest, command_id='new-register')]:
        with pytest.raises(ValueError, match='m1_corpus_approval_required'): call()
    assert decide(tmp_path, case['corpus_binding']) == approved
    assert store.read_head(tmp_path)['id'] == rejected['receipt']['id']
    assert resume_project(tmp_path)['action'] == 'await_approval'
    decide(tmp_path, case['corpus_binding'], command='reapprove')
    assert resume_project(tmp_path)['action'] == 'write_outputs'
    assert register_outputs(tmp_path, packet_id=packet['id'], submission=manifest, command_id='register')['status'] == 'review_pending'


@pytest.mark.parametrize('path', ['literature/shortlist.jsonl', 'literature/candidates.jsonl', 'scope/constraints.json'])
def test_changed_registered_corpus_needs_explicit_new_decision(tmp_path, path):
    case = fixture(tmp_path)
    decide(tmp_path, case['corpus_binding'])
    checkpoint(tmp_path, node='extract')
    packet = prepare_node(tmp_path, 'extract', command_id='prepared')['packet']
    checkpoint(tmp_path, files={path: corpus_files()[path]})  # Same bytes, new registered revision.
    new = api().current_corpus(tmp_path)
    assert new['corpus_binding'] != case['corpus_binding']
    assert resume_project(tmp_path)['action'] == 'await_approval'
    with pytest.raises(ValueError, match='m1_corpus_binding_changed'):
        decide(tmp_path, case['corpus_binding'], command='stale')
    with pytest.raises(ValueError, match='m1_corpus_approval_required'):
        prepare_node(tmp_path, 'extract', command_id='stale-prepare')
    decide(tmp_path, new['corpus_binding'], command='new-approve')
    with pytest.raises(ValueError, match='m1_input_binding_changed'):
        prepare_node(tmp_path, 'extract', command_id='old-packet')


def test_synthetic_evidence_helper_registers_extraction_but_preserves_review_gate(tmp_path):
    api()
    case = build_evidence_case(tmp_path)
    head = store.read_head(tmp_path)
    assert head['state']['content_origin'] == 'synthetic'
    assert head['state']['current_node_id'] == 'synthesize'
    assert resume_project(tmp_path)['action'] == 'await_review'
    assert any(ref['logical_path'] == 'knowledge/extractions.jsonl' for ref in case['artifact_refs'])
    assert api().current_corpus(tmp_path)['corpus_binding'] == case['corpus_binding']


@pytest.mark.parametrize('field,value', [('decision', 'revoke'), ('note', ' '), ('corpus_binding', 'bad'), ('command_id', '')])
def test_invalid_decisions_do_not_write(tmp_path, field, value):
    case = fixture(tmp_path)
    kwargs = {'corpus_binding': case['corpus_binding'], 'decision': 'approve', 'note': 'test', 'command_id': 'new'}
    kwargs[field] = value
    before = snapshot(tmp_path)
    with pytest.raises(ValueError): api().record_corpus_approval(tmp_path, **kwargs)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('phase', ['before_head', 'after_head'])
def test_decision_recovers_one_visible_record_after_interruption(tmp_path, monkeypatch, phase):
    case = fixture(tmp_path)
    original = store._atomic_head
    def fail(base, commit_id):
        if phase == 'after_head': original(base, commit_id)
        raise OSError('simulated interruption')
    monkeypatch.setattr(store, '_atomic_head', fail)
    with pytest.raises(OSError): decide(tmp_path, case['corpus_binding'])
    monkeypatch.setattr(store, '_atomic_head', original)
    result = decide(tmp_path, case['corpus_binding'])
    assert len(result['receipt']['state']['approvals']) == 1
    assert decide(tmp_path, case['corpus_binding']) == result


def test_cli_records_user_decision_and_replays_across_processes(tmp_path):
    case = fixture(tmp_path)
    command = [sys.executable, '-m', 'researchclaw.codex.cli', 'm1', 'corpus', 'decide', str(tmp_path),
               '--binding', case['corpus_binding'], '--decision', 'approve', '--note', '합성 검사 자료',
               '--command-id', 'cli', '--json']
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_approval_refuses_invalid_registered_corpus_without_state_change(tmp_path):
    case = fixture(tmp_path)
    checkpoint(tmp_path, files={'literature/shortlist.jsonl': b'{"source_id":"unknown"}\n'})
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='m1_corpus_invalid'):
        decide(tmp_path, case['corpus_binding'])
    assert snapshot(tmp_path) == before


def test_forged_authority_or_incomplete_record_does_not_authorize_extraction(tmp_path):
    case = fixture(tmp_path)
    decide(tmp_path, case['corpus_binding'])
    head = store.read_head(tmp_path)
    head['state']['current_node_id'] = 'extract'
    head['state']['approvals'][-1]['actor'] = 'coordinator'
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture-bad-authority',
        state=head['state'], event={**store._VERSION, 'type': 'synthetic_test_checkpoint', 'payload': {}}, objects={})
    assert resume_project(tmp_path)['action'] == 'await_approval'
    with pytest.raises(ValueError, match='m1_approval_record_invalid'):
        prepare_node(tmp_path, 'extract', command_id='cannot-prepare')


def test_extraction_content_failure_does_not_register_artifact_and_can_be_corrected(tmp_path):
    case = fixture(tmp_path)
    decide(tmp_path, case['corpus_binding'])
    checkpoint(tmp_path, node='extract')
    packet = prepare_node(tmp_path, 'extract', command_id='prepared')['packet']
    files = extraction_files(store.read_head(tmp_path)['state']['project_id'])
    invalid = files | {'knowledge/extractions.jsonl': b'{"claim_id":"unsupported"}\n'}
    result = register_outputs(tmp_path, packet_id=packet['id'], submission=submission(tmp_path, packet, invalid), command_id='invalid')
    assert result['status'] == 'draft_invalid'
    assert not result['artifacts']
    assert not any(ref['logical_path'].startswith('knowledge/') for ref in store.read_head(tmp_path)['state']['artifacts'])
    assert api().current_corpus(tmp_path)['corpus_binding'] == case['corpus_binding']
    result = register_outputs(tmp_path, packet_id=packet['id'], submission=submission(tmp_path, packet, files), command_id='valid')
    assert result['status'] == 'review_pending'


def test_registered_snapshot_mutation_cannot_be_approved_under_old_digest(tmp_path, monkeypatch):
    case = fixture(tmp_path)
    target = store.read_head(tmp_path)['state']['artifacts'][0]['sha256']
    original = store._read_file
    from researchclaw.core.m1 import approvals
    original_corpus = approvals._corpus
    def corpus_with_changed_object(root, head):
        def changed_read(path):
            data = original(path)
            return data + b'\nchanged' if path.name == target else data
        monkeypatch.setattr(store, '_read_file', changed_read)
        try:
            return original_corpus(root, head)
        finally:
            monkeypatch.setattr(store, '_read_file', original)
    monkeypatch.setattr(approvals, '_corpus', corpus_with_changed_object)
    with pytest.raises(ValueError, match='m1_input_content_changed'):
        decide(tmp_path, case['corpus_binding'])


def test_registered_extraction_replay_never_unrejects_later_decision(tmp_path):
    case = fixture(tmp_path)
    decide(tmp_path, case['corpus_binding'])
    checkpoint(tmp_path, node='extract')
    prepared = prepare_node(tmp_path, 'extract', command_id='prepared')
    packet = prepared['packet']
    files = extraction_files(store.read_head(tmp_path)['state']['project_id'])
    manifest = submission(tmp_path, packet, files)
    result = register_outputs(tmp_path, packet_id=packet['id'], submission=manifest, command_id='registered')
    rejected = decide(tmp_path, case['corpus_binding'], 'reject', 'reject')
    for ref in manifest['files'].values(): (tmp_path / ref['path']).unlink()
    assert register_outputs(tmp_path, packet_id=packet['id'], submission=manifest, command_id='registered') == result
    assert prepare_node(tmp_path, 'extract', command_id='prepared') == prepared
    assert store.read_head(tmp_path)['id'] == rejected['receipt']['id']
    assert resume_project(tmp_path)['action'] == 'await_approval'
    with pytest.raises(ValueError, match='m1_corpus_approval_required'):
        register_outputs(tmp_path, packet_id=packet['id'], submission=manifest, command_id='alias')


def test_boolean_approval_schema_version_is_not_a_valid_user_record(tmp_path):
    case = fixture(tmp_path)
    decide(tmp_path, case['corpus_binding'])
    head = store.read_head(tmp_path)
    head['state']['current_node_id'] = 'extract'
    head['state']['approvals'][-1]['schema_version'] = True
    store.commit_record(tmp_path, expected_head=head['id'], command_id='fixture-bool-schema',
        state=head['state'], event={**store._VERSION, 'type': 'synthetic_test_checkpoint', 'payload': {}}, objects={})
    with pytest.raises(ValueError, match='m1_approval_record_invalid'):
        prepare_node(tmp_path, 'extract', command_id='cannot-prepare')
