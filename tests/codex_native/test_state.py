from dataclasses import replace

from researchclaw.core.models import ProjectState, StageStatus
from researchclaw.core.state import StateStore


def test_state_round_trip_is_independent_of_conversation(tmp_path):
    store = StateStore(tmp_path)
    original = ProjectState.new("rc-test", "Materials property prediction", "materials_ai")
    store.save(original)

    loaded = StateStore(tmp_path).load()

    assert loaded == original
    assert loaded.schema_version == 1
    assert loaded.current_stage == 1
    assert loaded.status is StageStatus.READY


def test_state_save_replaces_existing_document_atomically(tmp_path):
    store = StateStore(tmp_path)
    state = ProjectState.new("rc-test", "Topic", "materials_ai")
    store.save(state)
    store.save(replace(state, current_stage=2, completed_stages=(1,)))

    loaded = store.load()

    assert loaded.current_stage == 2
    assert loaded.completed_stages == (1,)
    assert not list(tmp_path.glob("state-*.tmp"))
