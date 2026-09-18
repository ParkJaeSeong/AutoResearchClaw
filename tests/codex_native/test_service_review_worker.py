import pytest
from researchclaw.codex.service_inbox import ServiceInbox
from researchclaw.codex.service_review_worker import run_delivery


def setup(tmp_path):
    inbox=ServiceInbox(tmp_path,'p')
    recipient=dict(work_id='w',role_id='domain',round_id='initial',input_revision='v1')
    packet={'answer_state':'stored','qa_ref':{'qa_id':'q'}}
    from researchclaw.core.research_graph import store
    row=inbox.put('r','answer',store._hash(store._canonical(packet)),recipient,packet)
    context=dict(recipient=recipient,active=True,milestone='M1',materials={'question':'test'},packet={})
    return inbox,row,context


def test_saved_review_recovers_delivery_without_second_execution(tmp_path):
    inbox,row,context=setup(tmp_path);calls=[]
    def reviewer(*args):
        calls.append(args)
        return {'answer':{'rationale':'evidence reviewed','recommendation':None}}
    result=run_delivery(inbox,row['id'],lambda:context,reviewer)
    assert result['state']=='review_complete'
    assert inbox.pending()==[]
    assert run_delivery(inbox,row['id'],lambda:context,reviewer)==result
    assert len(calls)==1
    assert calls[0][3]['service_result']==row['result_ref']


def test_stopped_work_never_calls_model(tmp_path):
    inbox,row,context=setup(tmp_path);context['active']=False
    result=run_delivery(inbox,row['id'],lambda:context,lambda *a:pytest.fail('called'))
    assert result['state']=='not_applicable'
    assert len(inbox.pending())==1


def test_late_result_is_saved_but_not_acknowledged(tmp_path):
    inbox,row,context=setup(tmp_path)
    def reviewer(*args):
        context['recipient']=dict(context['recipient'],input_revision='v2')
        return {'answer':{'rationale':'old result','recommendation':None}}
    result=run_delivery(inbox,row['id'],lambda:context,reviewer)
    assert result['state']=='superseded'
    assert len(inbox.pending())==1


def test_failed_attempt_is_not_automatically_reexecuted(tmp_path):
    inbox,row,context=setup(tmp_path);calls=[]
    def fail(*args):calls.append(1);raise RuntimeError('host failure')
    with pytest.raises(RuntimeError):run_delivery(inbox,row['id'],lambda:context,fail)
    with pytest.raises(ValueError,match='inspection'):
        run_delivery(inbox,row['id'],lambda:context,fail)
    assert len(calls)==1


def test_initial_round_rejects_disclosed_peer_opinions(tmp_path):
    inbox,row,context=setup(tmp_path)
    context['packet']={'disclosed_initials':[{'answer':'peer'}]}
    with pytest.raises(ValueError,match='independent'):
        run_delivery(inbox,row['id'],lambda:context,lambda *a:pytest.fail('called'))
