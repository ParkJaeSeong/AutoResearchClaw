import pytest
from tests.codex_native.test_work_execution import ready_followup,apply
from tests.codex_native.research_graph.test_atlas_service import Atlas
from researchclaw.codex.atlas_session import AtlasSession
from researchclaw.codex.followup_review import review_followup
from researchclaw.core.research_graph import store


def prepared(root):
    ready_followup(root);client=Atlas();session=AtlasSession(root,client);session.bind('P','test')
    return session,client


def test_answer_to_assigned_review_without_duplicate_model_execution(tmp_path):
    session,client=prepared(tmp_path);calls=[]
    def reviewer(role,phase,packet,materials,run):
        calls.append((role,phase,materials))
        assert 'Evidence answer' in materials['atlas_qa_raw']
        assert materials['purpose']=='Which conditions remain unknown?'
        return {'answer':{'rationale':'synthetic review','recommendation':None}}
    first=review_followup(session,'next1',reviewer)
    second=review_followup(session,'next1',reviewer)
    assert first==second
    assert first['state']=='review_complete'
    assert len(calls)==1
    assert calls[0][:2]==('methodology','initial')
    row=store.read_head(tmp_path)['state']['service_followups']['next1']
    work=store.read_head(tmp_path)['state']['work_episodes'][row['target_work_id']]
    assert len(work['notes'])==1
    assert work['conclusion'] is None
    assert len(client.jobs)==1


def test_diagnostic_answer_never_starts_scientific_review(tmp_path):
    from researchclaw.codex.service_followup_runner import run_followup
    session,client=prepared(tmp_path)
    result=run_followup(session,'next1')
    row=session._get(result['request_key'])
    session._update(result['request_key'],job=dict(row['job'],status='failed'))
    result=review_followup(session,'next1',lambda *a:pytest.fail('must not review'))
    assert result['state']=='needs_input'


def test_stop_during_review_preserves_output_without_adoption(tmp_path):
    session,client=prepared(tmp_path)
    def reviewer(*args):
        apply(tmp_path,'work.execution.policy',dict(milestone='M1',status='stopped',reason='stop'),'stop')
        return {'answer':{'rationale':'late review','recommendation':None}}
    result=review_followup(session,'next1',reviewer)
    assert result['state']=='superseded'
    work=store.read_head(tmp_path)['state']['service_followups']['next1']['target_work_id']
    assert store.read_head(tmp_path)['state']['work_episodes'][work]['notes']==[]
