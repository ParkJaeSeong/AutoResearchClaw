import pytest
from tests.codex_native.research_graph.test_atlas_question import prepared
from researchclaw.core.research_graph import store


def test_outcome_requires_completed_council_and_preserves_final_refs(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_advance import advance_request
    from researchclaw.codex.atlas_council import run_council
    from researchclaw.codex.atlas_outcome import record_outcome
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q);advance_request(s,'k')
    outcome=dict(title='Keep comparison limited',conclusion='Collect electrode diagrams',rationale='No direct transfer',limitations=['Unknown injection geometry'],next_action='collect_materials',prior_ref=None,next_question=None)
    with pytest.raises(ValueError,match='atlas_council_incomplete'):record_outcome(s,'k',outcome)
    def reviewer(role,phase,packet,materials,run):
        return dict(answer=dict(rationale='Need geometry evidence',recommendation='ready_with_limits' if phase=='final' else None),host_id='test',model_id='synthetic')
    council=run_council(s,'k',reviewer)
    before=store.read_head(tmp_path)['id']
    with pytest.raises(ValueError,match='external_decision_prior_invalid'):
        record_outcome(s,'k',dict(outcome,prior_ref={}))
    assert store.read_head(tmp_path)['id']==before
    assert not list(s.base.glob('council-*/outcome-input.json'))
    result=record_outcome(s,'k',outcome)
    record=store.read_head(tmp_path)['state']['external_decisions'][result['decision_ref']['artifact_id']]
    assert record['review_status']=='council_final'
    assert record['submission_refs']==council['submission_refs']
    assert result['next_action']=='collect_materials'
    before=store.read_head(tmp_path)['id']
    assert record_outcome(s,'k',outcome)==result
    assert store.read_head(tmp_path)['id']==before
    with pytest.raises(ValueError,match='atlas_outcome_conflict'):record_outcome(s,'k',dict(outcome,conclusion='Changed'))


def test_invalid_followup_is_rejected_before_any_commit(tmp_path):
    from researchclaw.codex.atlas_outcome import record_outcome
    s,c,q=prepared(tmp_path)
    before=store.read_head(tmp_path)['id']
    with pytest.raises(ValueError,match='atlas_outcome_invalid'):
        record_outcome(s,'k',dict(title='Title',conclusion='Conclusion',rationale='Reason',limitations=[],next_action='followup_atlas',prior_ref=None,next_question={'question':'Incomplete'}))
    assert store.read_head(tmp_path)['id']==before


def test_unhashable_action_is_input_error(tmp_path):
    from researchclaw.codex.atlas_outcome import record_outcome
    s,c,q=prepared(tmp_path)
    with pytest.raises(ValueError,match='atlas_outcome_invalid'):
        record_outcome(s,'k',dict(title='Title',conclusion='Conclusion',rationale='Reason',limitations=[],next_action=[],prior_ref=None,next_question=None))
