from tests.codex_native.test_knowledge_session import Transport
from tests.codex_native.test_knowledge_protocol import INSTANCE,REQUEST
from researchclaw.codex.knowledge_session import KnowledgeSession
from researchclaw.codex.service_inbox import ServiceInbox


def test_stage_delivery_keeps_answer_once_and_update_history(tmp_path):
    s=KnowledgeSession(tmp_path,Transport(),INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    s.submit(REQUEST);s.observe(REQUEST['request_key'])
    inbox=ServiceInbox(tmp_path,'pilot-test')
    target=dict(work_id='w',role_id='methodology',round_id='initial',input_revision='v1')
    s.deliver_saved(REQUEST['request_key'],inbox,target)
    s.resume(REQUEST['request_key'],4);s.observe(REQUEST['request_key'])
    s.deliver_saved(REQUEST['request_key'],inbox,target)
    rows=inbox.pending()
    assert len(rows)==3
    assert len([r for r in rows if r['stage']=='answer'])==1
    assert len([r for r in rows if r['stage']=='knowledge'])==2


def test_offline_ui_projection_excludes_payload_and_credentials(tmp_path):
    from researchclaw.codex.knowledge_view import knowledge_status
    s=KnowledgeSession(tmp_path,Transport(),INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    s.submit(REQUEST);s.observe(REQUEST['request_key'])
    rows=knowledge_status(tmp_path.resolve())
    assert rows[0]['stored_answer'] is True
    assert rows[0]['knowledge_status']=='partial'
    assert 'payload' not in rows[0] and 'receipt' not in rows[0]


def test_answer_delivery_contains_verified_qa_for_worker(tmp_path):
    s=KnowledgeSession(tmp_path,Transport(),INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    s.submit(REQUEST);s.observe(REQUEST['request_key'])
    inbox=ServiceInbox(tmp_path,'pilot-test')
    target=dict(work_id='w',role_id='methodology',round_id='initial',input_revision='v1')
    s.deliver_saved(REQUEST['request_key'],inbox,target)
    answer=next(r for r in inbox.pending() if r['stage']=='answer')['result_ref']
    assert answer['answer_state']=='stored'
    assert 'schema_version: 1' in answer['atlas_qa_raw']


def test_status_endpoint_can_show_records_without_connection(tmp_path,monkeypatch):
    from researchclaw.codex.atlas_service_http import dispatch
    s=KnowledgeSession(tmp_path,Transport(),INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    s.submit(REQUEST);s.observe(REQUEST['request_key'])
    monkeypatch.delenv('PILOT_ATLAS_CONNECTION_FILE',raising=False)
    status=dispatch(tmp_path,'service-status',{})
    assert status['knowledge_jobs'][0]['stored_answer'] is True


def test_ui_local_module_imports_are_served():
    import re
    from researchclaw.codex.research_viewer import _STATIC, _STATIC_ROOT
    for filename, _ in _STATIC.values():
        if filename.endswith('.js'):
            text = (_STATIC_ROOT / filename).read_text()
            for dependency in re.findall(r"from\s+['\"]\./([^'\"]+\.js)['\"]", text):
                assert '/' + dependency in _STATIC, (filename, dependency)
