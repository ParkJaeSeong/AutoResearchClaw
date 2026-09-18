"""Request reporting uses real graph/journal state and a synthetic remote."""
import json
import pytest
from researchclaw.core.research_graph import store
from researchclaw.codex.atlas_question import ask_research_question
from researchclaw.codex.atlas_advance import advance_request
from tests.codex_native.research_graph.test_atlas_question import prepared


def episodes(s):
    return list(store.read_head(s.root)['state'].get('work_episodes', {}).values())


def test_lost_send_resumes_one_request_episode_and_completion_is_immutable(tmp_path):
    s,c,q=prepared(tmp_path); c.lose=True
    with pytest.raises(ValueError): ask_research_question(s,'k',q)
    assert len(episodes(s)) == 1
    assert episodes(s)[0]['execution_status'] == 'running'
    assert episodes(s)[0]['review_required'] is False
    ask_research_question(s,'k',q)
    result=advance_request(s,'k')
    episode=episodes(s)[0]
    assert len(episodes(s)) == 1 and len(c.jobs) == 1
    assert episode['execution_status'] == 'finished'
    assert result['packet_sha256'] in json.dumps(episode)
    assert result['packet']['evidence_ref']['artifact_id'] in json.dumps(episode)
    assert '과학적' in episode['conclusion']['remaining']
    head=store.read_head(tmp_path)['id']
    assert advance_request(s,'k') == result
    ask_research_question(s,'k',q)
    assert store.read_head(tmp_path)['id'] == head


@pytest.mark.parametrize('status,attention', [('queued',False),('running',False),('queued',True),('failed',True)])
def test_repeated_wait_and_attention_are_deduplicated_and_resumable(tmp_path,status,attention):
    s,c,q=prepared(tmp_path); ask_research_question(s,'k',q)
    c.jobs['k']['status']=status
    if attention: c.jobs['k'].update(detail={},scheduled=False)
    result=advance_request(s,'k')
    assert result['stage'] == ('needs_attention' if attention else 'waiting_for_atlas')
    assert len(episodes(s)) == 1
    assert episodes(s)[0]['conclusion'] is None
    head=store.read_head(tmp_path)['id']
    assert advance_request(s,'k') == result
    assert store.read_head(tmp_path)['id'] == head


@pytest.mark.parametrize('status', ['partial','failed','interrupted'])
def test_diagnostic_input_finishes_reception_without_scientific_success(tmp_path,status):
    s,c,q=prepared(tmp_path); ask_research_question(s,'k',q)
    c.jobs['k']['status']=status
    result=advance_request(s,'k')
    episode=episodes(s)[0]
    assert result['packet']['execution']['review_purpose'] == 'diagnostic_or_limited_review'
    assert episode['execution_status']=='finished'
    assert '진단' in episode['conclusion']['judgment']


def test_unknown_and_changed_key_create_no_episode(tmp_path):
    s,c,q=prepared(tmp_path)
    with pytest.raises(ValueError): ask_research_question(s,'k','unknown')
    assert not episodes(s)
    ask_research_question(s,'k',q)
    head=store.read_head(tmp_path)['id']
    with pytest.raises(ValueError): ask_research_question(s,'k','changed')
    assert store.read_head(tmp_path)['id']==head


def test_remote_errors_and_job_detail_never_enter_public_episode(tmp_path):
    s,c,q=prepared(tmp_path); ask_research_question(s,'k',q)
    def denied(*args,**kwargs): raise ValueError('token=SECRET-raw')
    original=c.identity; c.identity=denied
    with pytest.raises(ValueError,match='SECRET'): advance_request(s,'k')
    assert 'SECRET' not in json.dumps(episodes(s))
    assert episodes(s)[0]['conclusion'] is None
    c.identity=original
    c.jobs['k'].update(status='queued',dispatch_error='SECRET-detail')
    advance_request(s,'k')
    assert 'SECRET' not in json.dumps(episodes(s))


def test_prejournal_failure_same_key_cannot_change_content(tmp_path,monkeypatch):
    s,c,q=prepared(tmp_path)
    original=s.ask
    def disk_failure(*args,**kwargs): raise OSError('SECRET-disk')
    monkeypatch.setattr(s,'ask',disk_failure)
    with pytest.raises(OSError): ask_research_question(s,'k',q)
    assert len(episodes(s))==1
    monkeypatch.setattr(s,'ask',original)
    # Another key parameter changes the intended request before any journal row exists.
    head=store.read_head(tmp_path)['id']
    with pytest.raises(ValueError): ask_research_question(s,'k',q,previous='different')
    assert store.read_head(tmp_path)['id']==head
    ask_research_question(s,'k',q)
    assert len(episodes(s))==1


def test_existing_completed_native_request_is_not_backfilled(tmp_path):
    s,c,q=prepared(tmp_path)
    # Represents a request completed by the previous runtime.
    s.ask('k','Existing question',q,research_context={'question_ref':{'artifact_id':q}})
    advance_request(s,'k')
    assert not episodes(s)
    head=store.read_head(tmp_path)['id']
    ask_research_question(s,'k',q)
    assert store.read_head(tmp_path)['id']==head


def test_committed_start_with_lost_receipt_resumes_without_duplicate(tmp_path,monkeypatch):
    from researchclaw.core.research_graph import commands
    s,c,q=prepared(tmp_path)
    original=commands.apply_command
    def lose_receipt(*args,**kwargs):
        receipt=original(*args,**kwargs)
        if kwargs['operation']=='episode.start':
            raise OSError('receipt lost')
        return receipt
    monkeypatch.setattr(commands,'apply_command',lose_receipt)
    with pytest.raises(OSError): ask_research_question(s,'k',q)
    assert len(episodes(s)) == 1 and not c.jobs
    monkeypatch.setattr(commands,'apply_command',original)
    ask_research_question(s,'k',q)
    assert advance_request(s,'k')['stage']=='review_input_ready'
    assert len(episodes(s))==1


def test_frozen_packet_with_missing_conclusion_resumes_offline(tmp_path,monkeypatch):
    from researchclaw.core.research_graph import commands
    s,c,q=prepared(tmp_path); ask_research_question(s,'k',q)
    original=commands.apply_command
    def fail_conclusion(*args,**kwargs):
        if kwargs['operation']=='episode.conclude': raise OSError('write unavailable')
        return original(*args,**kwargs)
    monkeypatch.setattr(commands,'apply_command',fail_conclusion)
    with pytest.raises(OSError): advance_request(s,'k')
    assert s._get('k')['review_input_sha256']
    assert episodes(s)[0]['conclusion'] is None
    monkeypatch.setattr(commands,'apply_command',original)
    def offline(*args,**kwargs): raise AssertionError('No remote call needed')
    c.identity=offline
    result=advance_request(s,'k')
    assert episodes(s)[0]['execution_status']=='finished'
    head=store.read_head(tmp_path)['id']
    assert advance_request(s,'k')==result
    assert store.read_head(tmp_path)['id']==head


def test_reporting_failure_never_masks_original_transport_error(tmp_path,monkeypatch):
    from researchclaw.core.research_graph import commands
    s,c,q=prepared(tmp_path); ask_research_question(s,'k',q)
    def denied(*args,**kwargs): raise PermissionError('SECRET-original')
    def disk_error(*args,**kwargs): raise OSError('secondary report failure')
    c.identity=denied
    monkeypatch.setattr(commands,'apply_command',disk_error)
    with pytest.raises(PermissionError,match='SECRET-original'): advance_request(s,'k')
    assert 'SECRET' not in json.dumps(episodes(s))
