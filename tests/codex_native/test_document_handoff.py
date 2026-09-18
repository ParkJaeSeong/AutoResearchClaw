import pytest
from concurrent.futures import ThreadPoolExecutor
from researchclaw.codex.document_handoff import HandoffJournal, HandoffConflict


def journal(tmp_path):
    return HandoffJournal(tmp_path / 'handoff.sqlite3', 'pilot-project', 'atlas-instance', 'pilot-consumer')


def enqueue(j, operation='convert.jats', key='paper-1'):
    return j.enqueue(operation, key, {'config_revision': 'v1', 'original_sha256': 'abc'},
                     {'atlas_project_id': 'knowledge-project', 'purpose': 'compare mixing'})


def receipt(task='task-1'):
    return {'instance_id': 'documents-instance', 'operation': 'convert.jats',
            'request_key': 'paper-1', 'request_sha256': 'server-hash',
            'receipt_id': 'receipt-1', 'task_id': task}


def event(sequence=1, event_id='event-1'):
    return dict(atlas_instance_id='atlas-instance', consumer_id='pilot-consumer',
                event_id=event_id, sequence=sequence, import_id='import-1',
                request_key='paper-1', result_ref={'hash': str(sequence)},
                phase='terminal', outcome='partial')


def accepted(j):
    enqueue(j)
    j.accept_documents('convert.jats', 'paper-1', receipt())
    j.accept_atlas('convert.jats', 'paper-1', {'import_id': 'import-1'})


def test_durable_two_outboxes_and_conflict(tmp_path):
    j = journal(tmp_path)
    assert enqueue(j) == enqueue(j)
    with pytest.raises(HandoffConflict):
        j.enqueue('convert.jats', 'paper-1', {'config_revision': 'v2'}, {})
    assert journal(tmp_path).pending()[0]['destination'] == 'documents'
    j.accept_documents('convert.jats', 'paper-1', receipt())
    pending = journal(tmp_path).pending()
    assert len(pending) == 1 and pending[0]['destination'] == 'atlas'
    assert pending[0]['documents_receipt']['task_id'] == 'task-1'
    j.accept_documents('convert.jats', 'paper-1', receipt())
    with pytest.raises(HandoffConflict):
        j.accept_documents('convert.jats', 'paper-1', receipt('other-task'))
    j.accept_atlas('convert.jats', 'paper-1', {'import_id': 'import-1'})
    assert journal(tmp_path).pending() == []


def test_operations_and_concurrent_enqueue_are_isolated(tmp_path):
    j = journal(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: enqueue(j), range(8)))
    enqueue(j, 'convert.file')
    assert len(j.pending()) == 2


def test_event_processing_precedes_ack_and_survives_restart(tmp_path):
    j = journal(tmp_path)
    accepted(j)
    j.receive(event())
    j.receive(event())
    assert len(j.pending_events()) == 1
    assert j.pending_acks() == []
    with pytest.raises(HandoffConflict):
        j.acknowledged(['event-1'])
    j.processed('event-1', {'saved_result_ref': {'hash': '1'}})
    assert journal(tmp_path).pending_acks() == ['event-1']
    j.acknowledged(['event-1'])
    j.receive(event())
    assert j.pending_acks() == []
    assert j.pending_events() == []


def test_reverse_events_do_not_replace_latest_and_identity_is_checked(tmp_path):
    j = journal(tmp_path)
    accepted(j)
    j.receive(event(2, 'event-2'))
    j.receive(event())
    assert j.latest('import-1')['sequence'] == 2
    with pytest.raises(HandoffConflict):
        j.receive({**event(), 'consumer_id': 'other'})
    with pytest.raises(HandoffConflict):
        j.receive({**event(), 'atlas_instance_id': 'clone'})
    with pytest.raises(HandoffConflict):
        j.receive({**event(), 'outcome': 'completed'})
    with pytest.raises(HandoffConflict):
        j.receive({**event(), 'event_id': 'unknown', 'import_id': 'unknown'})


def test_database_cannot_be_rebound_to_another_project(tmp_path):
    journal(tmp_path)
    with pytest.raises(HandoffConflict):
        HandoffJournal(tmp_path / 'handoff.sqlite3', 'other', 'atlas-instance', 'pilot-consumer')


def test_ack_batch_rolls_back_if_any_event_is_unprocessed(tmp_path):
    j = journal(tmp_path)
    accepted(j)
    j.receive(event())
    j.receive(event(2, 'event-2'))
    j.processed('event-1', {'saved': True})
    with pytest.raises(HandoffConflict):
        j.acknowledged(['event-1', 'event-2'])
    assert j.pending_acks() == ['event-1']


def test_out_of_order_receipts_and_changed_processing_are_rejected(tmp_path):
    j = journal(tmp_path)
    enqueue(j)
    with pytest.raises(HandoffConflict):
        j.accept_atlas('convert.jats', 'paper-1', {'import_id': 'import-1'})
    assert j.pending()[0]['destination'] == 'documents'
    accepted(j)
    j.receive(event())
    j.processed('event-1', {'saved': 'original'})
    with pytest.raises(HandoffConflict):
        j.processed('event-1', {'saved': 'changed'})
    assert j.pending_acks() == ['event-1']
