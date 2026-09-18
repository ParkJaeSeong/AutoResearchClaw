import pytest
from researchclaw.codex.document_handoff_runner import configured_adapter, cycle
from researchclaw.codex.document_handoff import HandoffJournal
from researchclaw.core.research_graph import commands, store


def test_runner_binds_real_project_identity_without_changing_head(tmp_path):
    commands.init_project(tmp_path,topic='Synthetic handoff',content_origin='synthetic')
    head=store.read_head(tmp_path)
    HandoffJournal(tmp_path/'.document-handoff/journal.sqlite3',head['state']['project_id'],'A','pilot')
    adapter=configured_adapter(tmp_path,tmp_path/'documents-private.json',tmp_path/'atlas-private.json')
    assert adapter.journal.identity['project_id']==head['state']['project_id']
    assert store.read_head(tmp_path)['id']==head['id']


def test_cycle_still_receives_existing_work_after_submission_failure():
    calls=[]
    class Journal:
        def pending(self):return []
        def pending_events(self):return []
        def pending_acks(self):return []
    class Adapter:
        journal=Journal()
        def advance(self):raise ValueError('supplier_not_ready')
        def poll(self):calls.append('poll')
    result=cycle(Adapter())
    assert calls==['poll'] and result['errors']==['supplier_not_ready']
