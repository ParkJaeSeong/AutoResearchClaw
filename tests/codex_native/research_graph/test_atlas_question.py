import pytest
from researchclaw.core.research_graph import store
from tests.codex_native.research_graph.test_atlas_service import session
from tests.codex_native.research_graph.test_external_evidence import apply, imported, ref, review_payload
from researchclaw.core.research_graph.views import build_view


def prepared(tmp_path):
    s, c = session(tmp_path)
    s.bind('P','Test'); imported(tmp_path)
    e=ref(build_view(tmp_path),'external_evidence')
    apply(tmp_path,'external.review.record',review_payload(e))
    r=ref(build_view(tmp_path),'external_reviews')
    apply(tmp_path,'external.decision.record',dict(review_ref=r,title='Prior',conclusion='Keep x axis',rationale='Direction unknown',limitations=['Unknown geometry'],submission_refs=[],prior_ref=None,producer_id='coordinator'))
    d=ref(build_view(tmp_path),'external_decisions')
    apply(tmp_path,'external.question.record',dict(decision_ref=d,question='Which direction?',missing_evidence='Electrode geometry',decision_impact='Keep or revise x axis',scope='Provided paper',producer_id='coordinator'))
    return s,c,ref(build_view(tmp_path),'external_questions')['artifact_id']


def test_native_question_context_reaches_actual_payload_and_survives_lost_response(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    s,c,q=prepared(tmp_path); c.lose=True
    with pytest.raises(ValueError):ask_research_question(s,'k',q)
    row=s._get('k')
    assert row['research_context']['question_ref']['artifact_id']==q
    assert 'Electrode geometry' in row['payload']['question']
    assert 'Keep or revise x axis' in row['payload']['question']
    assert 'Keep x axis' in row['payload']['question']
    assert row['payload']['client_context']['question_id']==q
    old=row['payload']
    apply(tmp_path,'external.question.record',dict(decision_ref=row['research_context']['question']['decision_ref'],question='Another?',missing_evidence='New gap',decision_impact='Other decision',scope='Other',producer_id='coordinator'))
    ask_research_question(s,'k',q)
    assert s._get('k')['payload']==old
    assert len(c.jobs)==1


def test_unknown_question_cannot_submit(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    s,c,q=prepared(tmp_path)
    with pytest.raises(ValueError,match='atlas_question_unknown'):ask_research_question(s,'k','not-native')
    assert not c.jobs


def test_request_key_cannot_switch_research_question(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    s,c,q=prepared(tmp_path)
    ask_research_question(s,'k',q)
    with pytest.raises(ValueError,match='atlas_request_conflict'):ask_research_question(s,'k','other')


def test_research_context_is_in_frozen_review_input(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_advance import advance_request
    s,c,q=prepared(tmp_path)
    ask_research_question(s,'k',q)
    result=advance_request(s,'k')
    assert result['packet']['research_context']['question_ref']['artifact_id']==q
