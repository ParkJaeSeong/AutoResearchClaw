import pytest
from researchclaw.codex.service_inbox import ServiceInbox


def target():
    return dict(work_id='w1',role_id='reviewer',round_id='initial',input_revision='v1')


def test_delivery_survives_restart_and_is_deduplicated(tmp_path):
    inbox=ServiceInbox(tmp_path,'project1')
    first=inbox.put('request1','answer','a'*64,target(),{'qa_id':'qa1'})
    again=ServiceInbox(tmp_path,'project1').put('request1','answer','a'*64,target(),{'qa_id':'qa1'})
    assert first==again
    assert len(inbox.pending())==1
    assert inbox.pending()[0]['state']=='delivery_pending'
    assert inbox.pending()[0]['result_ref']=={'qa_id':'qa1'}


def test_wrong_recipient_cannot_acknowledge(tmp_path):
    inbox=ServiceInbox(tmp_path,'project1')
    row=inbox.put('request1','answer','a'*64,target(),{})
    with pytest.raises(ValueError,match='target_mismatch'):
        inbox.acknowledge(row['id'],dict(target(),input_revision='v2'))
    assert len(inbox.pending())==1
    inbox.acknowledge(row['id'],target())
    inbox.acknowledge(row['id'],target())
    assert inbox.pending()==[]


def test_stage_results_do_not_hide_each_other_and_conflicts_rejected(tmp_path):
    inbox=ServiceInbox(tmp_path,'project1')
    inbox.put('request1','answer','a'*64,target(),{'qa_id':'qa1'})
    inbox.put('request1','knowledge','b'*64,target(),{'attempt':1})
    assert len(inbox.pending())==2
    with pytest.raises(ValueError,match='result_conflict'):
        inbox.put('request1','answer','a'*64,target(),{'qa_id':'changed'})
    assert len(inbox.pending())==2


def test_project_binding_cannot_be_reused(tmp_path):
    ServiceInbox(tmp_path,'project1')
    with pytest.raises(ValueError,match='project_mismatch'):
        ServiceInbox(tmp_path,'project2')
