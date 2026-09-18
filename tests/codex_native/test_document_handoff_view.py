import pytest
from researchclaw.codex.document_handoff import HandoffJournal
from researchclaw.codex.document_handoff_view import build_handoff_view


def test_absent_journal_is_empty_without_creating_files(tmp_path):
    assert build_handoff_view(tmp_path, 'P')['items'] == []
    assert list(tmp_path.iterdir()) == []


def test_projection_separates_receipt_from_conversion_and_redacts(tmp_path):
    j = HandoffJournal(tmp_path / '.document-handoff/journal.sqlite3', 'P', 'A', 'C')
    j.enqueue('convert.file', 'k', {'token': 'secret', 'filename': 'paper.pdf'},
              {'bibliography': {'title': '논문'}, 'purpose': '혼련 비교', 'token': 'secret'})
    view = build_handoff_view(tmp_path, 'P')
    assert view['items'][0]['status'] == 'submission_pending'
    assert 'secret' not in str(view)
    j.accept_documents('convert.file', 'k', {'operation': 'convert.file', 'request_key': 'k', 'task_id': 't'})
    assert build_handoff_view(tmp_path, 'P')['items'][0]['status'] == 'atlas_submission_pending'
    j.accept_atlas('convert.file', 'k', {'import_id': 'i'})
    j.receive(dict(atlas_instance_id='A', consumer_id='C', event_id='e', sequence=1,
                   import_id='i', request_key='k', phase='terminal', outcome='partial', result_ref={}))
    item = build_handoff_view(tmp_path, 'P')['items'][0]
    assert item['status'] == 'partial'
    assert item['pilot_review'] == 'unrecorded'
    with pytest.raises(ValueError):
        build_handoff_view(tmp_path, 'other')


def test_http_read_only_route_rejects_historical_head_and_serves_module(tmp_path):
    import json
    import threading
    from tests.codex_native.research_graph.test_viewer import api, fetch, Fixture
    f = Fixture(tmp_path / 'project')
    server = api()._make_server(f.root, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, _ = fetch(server, '/api/document-handoffs')
        assert status == 200 and json.loads(body)['items'] == []
        assert fetch(server, '/api/document-handoffs?head=' + '0' * 64)[0] == 400
        assert fetch(server, '/document_handoff.js')[0] == 200
        assert not (f.root / '.document-handoff').exists()
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_review_projection_includes_saved_conclusion_not_private_packet(tmp_path):
    import json,hashlib
    from researchclaw.codex.document_handoff import _json
    j=HandoffJournal(tmp_path/'.document-handoff/journal.sqlite3','P','A','C')
    j.enqueue('convert.file','k',{'filename':'paper.pdf'},{'bibliography':{'title':'논문'}})
    j.accept_documents('convert.file','k',{'operation':'convert.file','request_key':'k','task_id':'t'})
    j.accept_atlas('convert.file','k',{'import_id':'i'})
    r={'stage':'review_complete','coordinator':{'answer':{'rationale':'제한적으로 사용합니다.','recommendation':'ready_with_limits'}},'rounds':{'initial':[{'role':'domain','answer':{'rationale':'첫 의견'}}]}}
    task={'id':'review','key':{'import_id':'i'},'status':'input_ready','context':{'question_revision':'q','question':'질문'},'packet':{'secret':'private'},'review_result':r,'review_result_sha256':hashlib.sha256(_json(r).encode()).hexdigest()}
    with j._db() as db:
        db.execute('CREATE TABLE import_reviews (id TEXT PRIMARY KEY,body TEXT NOT NULL)');db.execute('INSERT INTO import_reviews VALUES (?,?)',('review',_json(task)))
    item=build_handoff_view(tmp_path,'P')['items'][0]
    assert item['pilot_review']=='review_complete'
    assert item['reviews'][0]['conclusion']=='제한적으로 사용합니다.'
    assert 'private' not in json.dumps(item)
