"""Advance real journal/import state; only the remote Atlas is simulated."""
import json

import pytest

from researchclaw.core.research_graph import store
from tests.codex_native.research_graph.test_atlas_service import session


def advance(s, key='k'):
    from researchclaw.codex.atlas_advance import advance_request
    return advance_request(s, key)


def test_completed_request_imports_once_and_freezes_shared_input(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test')
    s.ask('k', 'Question?', 'q1')
    result = advance(s)
    assert result['stage'] == 'review_input_ready'
    assert result['packet']['question'] == 'Question?'
    assert result['packet']['qa']['answer'] == 'Evidence answer'
    assert result['packet']['evidence_ref']['artifact_id'] in store.read_head(tmp_path)['state']['external_evidence']
    assert 'external_reviews' not in store.read_head(tmp_path)['state'] or not store.read_head(tmp_path)['state']['external_reviews']
    head = store.read_head(tmp_path)['id']
    # Restart and even loss of service must not repeat a completed import.
    def offline(*args, **kwargs):
        raise AssertionError('No remote work after frozen input')
    client.identity = offline
    assert advance(s) == result
    assert store.read_head(tmp_path)['id'] == head
    assert json.loads((s.base/'objects'/result['packet_sha256']).read_bytes()) == result['packet']


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_running_preserves_graph_and_does_not_claim_review_ready(tmp_path, status):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = status
    # A diagnostic QA ref on a nonterminal job is not a final answer.
    before = store.read_head(tmp_path)['id']
    assert advance(s)['stage'] == 'waiting_for_atlas'
    assert store.read_head(tmp_path)['id'] == before


@pytest.mark.parametrize('status', ['failed', 'interrupted', 'completed'])
def test_terminal_without_qa_requires_inspection_not_endless_wait(tmp_path, status):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = status
    client.jobs['k']['detail'] = {}
    result = advance(s)
    assert result['stage'] == 'needs_attention'
    assert result['reason'] == 'terminal_qa_missing'
    assert result['retryable'] is False
    assert not s.status()['requests'][0]['received']


def test_partial_qa_is_retained_with_status_not_promoted_to_success(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = 'partial'
    result = advance(s)
    assert result['packet']['atlas_status'] == 'partial'
    assert result['stage'] == 'review_input_ready'


def test_resume_lost_submission_uses_original_key(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); client.lose = True
    with pytest.raises(ValueError): s.ask('k', 'Question?', 'q1')
    result = advance(s)
    assert result['stage'] == 'review_input_ready'
    assert len(client.jobs) == 1


def test_corrupted_frozen_packet_is_rejected(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    result = advance(s)
    (s.base/'objects'/result['packet_sha256']).write_text('{}')
    with pytest.raises(ValueError, match='atlas_raw_invalid'): advance(s)


def test_cli_watch_advances_running_job_then_stops_at_review_input(tmp_path, monkeypatch):
    from researchclaw.codex.cli import build_parser
    from researchclaw.codex import atlas_service_cli, atlas_service_http
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = 'running'
    monkeypatch.setattr(atlas_service_http, 'configured_session', lambda root: s)
    def complete(interval):
        assert interval == 2
        client.jobs['k']['status'] = 'completed'
    monkeypatch.setattr(atlas_service_cli.time, 'sleep', complete)
    args = build_parser().parse_args(['research', 'atlas-service', 'advance', str(tmp_path), '--key', 'k', '--watch', '--interval', '2'])
    result = atlas_service_cli.run(args)
    assert result['stage'] == 'review_input_ready'
    assert len(store.read_head(tmp_path)['state']['external_evidence']) == 1


def test_concurrent_advance_yields_without_mutating(tmp_path):
    import fcntl
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    before = store.read_head(tmp_path)['id']
    with (s.base/'advance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='atlas_advance_busy') as caught:
            advance(s)
        assert caught.value.retryable
    assert store.read_head(tmp_path)['id'] == before


@pytest.mark.parametrize('status', ['failed', 'interrupted'])
def test_diagnostic_qa_keeps_failed_execution_in_review_packet(tmp_path, status):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = status
    result = advance(s)
    assert result['packet']['atlas_status'] == status
    assert result['packet']['review_boundary']['scientific_review_completed'] is False


def test_new_supporting_downloads_do_not_silently_change_frozen_input(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    result = advance(s)
    s._update('k', supporting=[{'kind':'page','received':False,'error':'later_observation'}])
    assert advance(s) == result


def test_unknown_job_state_does_not_import_qa(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = 'new_future_state'
    with pytest.raises(ValueError, match='atlas_job_status_unknown'): advance(s)
    assert not s.status()['requests'][0]['received']


@pytest.mark.parametrize('status, scheduled, error', [('queued', False, None), ('queued', True, 'spawn failed'), ('running', True, 'worker missing')])
def test_dispatch_diagnostics_stop_automatic_wait(tmp_path, status, scheduled, error):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k'].update(status=status, scheduled=scheduled, dispatch_error=error)
    result = advance(s)
    assert result['stage'] == 'needs_attention'
    assert result['reason'] == 'execution_needs_inspection'
    assert not s.status()['requests'][0]['received']


def test_partial_failure_reasons_are_available_to_reviewer(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = 'partial'
    client.jobs['k']['detail']['issues'] = ['source unavailable']
    result = advance(s)
    assert result['packet']['execution']['issues'] == ['source unavailable']
    assert result['packet']['execution']['receipt_ref']['request_key'] == 'k'


@pytest.mark.parametrize('cached_only', [False, True])
def test_manual_active_qa_cannot_bypass_terminal_check(tmp_path, cached_only):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    # Build an already-cached legacy state; current receive rejects active jobs.
    s.receive('k', store.read_head(tmp_path)['id'])
    client.jobs['k']['status'] = 'running'
    s.poll('k')
    if cached_only: s._update('k', received=False, import_result=None)
    assert advance(s)['stage'] == 'waiting_for_atlas'
    assert 'review_input_sha256' not in s._get('k')


def test_received_terminal_can_prepare_input_offline(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    s.receive('k', store.read_head(tmp_path)['id'])
    def offline(*args, **kwargs): raise AssertionError('Already received terminal QA')
    client.identity = offline
    assert advance(s)['stage'] == 'review_input_ready'


def test_cached_active_qa_must_match_final_reference(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    # Build an already-cached legacy state; current receive rejects active jobs.
    s.receive('k', store.read_head(tmp_path)['id'])
    client.jobs['k']['status'] = 'running'
    s.poll('k')
    client.jobs['k']['status'] = 'completed'
    client.jobs['k']['detail']['qa_ref'] = {'qa_id':'qa-new', 'sha256':'b'*64}
    with pytest.raises(ValueError, match='atlas_reference_mismatch'): advance(s)
    assert 'review_input_sha256' not in s._get('k')


def test_current_receive_rejects_active_qa_before_import(tmp_path):
    s, client = session(tmp_path)
    s.bind('P', 'Test'); s.ask('k', 'Question?', 'q1')
    client.jobs['k']['status'] = 'running'
    head = store.read_head(tmp_path)['id']
    with pytest.raises(ValueError, match='atlas_qa_not_ready'):
        s.receive('k', head)
    assert store.read_head(tmp_path)['id'] == head
    assert not s._get('k').get('received')
