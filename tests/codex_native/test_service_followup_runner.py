import pytest
from tests.codex_native.test_work_execution import ready_followup,apply
from tests.codex_native.research_graph.test_atlas_service import Atlas
from researchclaw.codex.atlas_session import AtlasSession
from researchclaw.codex.service_followup_runner import run_followup
from researchclaw.core.research_graph import store


def test_followup_submits_one_remote_job_and_recovers_lost_response(tmp_path):
    ready_followup(tmp_path);client=Atlas();session=AtlasSession(tmp_path,client);session.bind('P','test')
    client.lose=True
    with pytest.raises(ValueError,match='transport'):run_followup(session,'next1')
    result=run_followup(session,'next1')
    assert result['state']=='result_stored'
    posts=client.posts
    assert run_followup(session,'next1')['job_id']==result['job_id']
    assert client.posts==posts
    assert len(client.jobs)==1
    assert len(store.read_head(tmp_path)['state']['work_episodes'])==2


def test_stopped_policy_does_not_submit(tmp_path):
    ready_followup(tmp_path);client=Atlas();session=AtlasSession(tmp_path,client);session.bind('P','test')
    apply(tmp_path,'work.execution.policy',dict(milestone='M1',status='stopped',reason='stop'),'stop')
    with pytest.raises(ValueError,match='execution_not_active'):run_followup(session,'next1')
    assert client.posts==0
