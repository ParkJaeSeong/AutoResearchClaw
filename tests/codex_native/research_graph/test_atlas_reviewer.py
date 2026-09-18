import json
import pytest


def test_reviewer_result_requires_observed_host_and_no_tools(tmp_path):
    from researchclaw.codex.atlas_reviewer import read_result
    (tmp_path/'answer.json').write_text(json.dumps(dict(rationale='Keep the limitation',recommendation=None)))
    events=[dict(type='thread.started',thread_id='t1'),dict(type='turn.completed')]
    (tmp_path/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    assert read_result(tmp_path,'initial')['host_id']=='codex-exec:t1'
    events.insert(1,dict(type='item.completed',item=dict(type='command_execution')))
    (tmp_path/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    with pytest.raises(ValueError,match='reviewer_tool_access'):read_result(tmp_path,'initial')


def test_initial_cannot_claim_final_recommendation(tmp_path):
    from researchclaw.codex.atlas_reviewer import read_result
    (tmp_path/'answer.json').write_text(json.dumps(dict(rationale='Premature conclusion',recommendation='ready')))
    (tmp_path/'events.jsonl').write_text('{"type":"thread.started","thread_id":"t1"}\n{"type":"turn.completed"}')
    with pytest.raises(ValueError,match='reviewer_answer_invalid'):read_result(tmp_path,'initial')


def test_completed_host_output_survives_crash_before_verified_save(tmp_path):
    from researchclaw.codex.atlas_reviewer import host_reviewer
    (tmp_path/'answer.json').write_text(json.dumps(dict(rationale='Preserved result',recommendation=None)))
    (tmp_path/'events.jsonl').write_text('{"type":"thread.started","thread_id":"t1"}\n{"type":"turn.completed"}')
    (tmp_path/'activity.json').write_text('{"status":"exited","returncode":0}')
    result=host_reviewer('/does/not/exist')('domain','initial',{}, {},tmp_path)
    assert result['answer']['rationale']=='Preserved result'
