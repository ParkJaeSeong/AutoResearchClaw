import hashlib
import pytest
from researchclaw.codex import source_review as review


def material():
    data=b"first\nmeasured at 23 C\nlast\n"
    return {"id":"S1", "title":"source", "text":data.decode(), "ref":{"sha256":hashlib.sha256(data).hexdigest()}}


def answer():
    return {"rationale":"judgment", "findings":[{"claim":"temperature reported", "kind":"observation", "citations":[{"source_id":"S1", "start_line":2,"end_line":2,"quote":"measured at 23 C"}]}], "questions":[],"answers":[],"unresolved":[],"decision":None}


def test_bad_quote_or_location_cannot_be_registered_as_evidence():
    assert hasattr(review,"validate_answer"), "source-grounded validation is missing"
    review.validate_answer(answer(),[material()],"initial",[])
    for changes in [{"quote":"not in source"},{"start_line":1,"end_line":1},{"source_id":"absent"}]:
        bad=answer();bad["findings"][0]["citations"][0].update(changes)
        with pytest.raises(ValueError):review.validate_answer(bad,[material()],"initial",[])


def test_final_must_answer_each_assigned_question_even_if_unresolved():
    assert hasattr(review,"validate_answer"), "response coverage is missing"
    a=answer();a["decision"]="insufficient"
    inbound=[{"id":"domain-q1","question":"same temperature?"}]
    with pytest.raises(ValueError,match="unanswered"):review.validate_answer(a,[material()],"final",inbound)
    a["answers"]=[{"question_id":"domain-q1","answer":"not established","citations":[],"status":"unresolved"}]
    review.validate_answer(a,[material()],"final",inbound)


def test_source_bytes_are_checked_before_excerpting():
    assert hasattr(review,"checked_text"), "source byte integrity is missing"
    m=material()
    assert review.checked_text(m["text"].encode(),m["ref"]["sha256"])==m["text"]
    with pytest.raises(ValueError,match="hash"):review.checked_text(b"changed",m["ref"]["sha256"])


def test_independent_packet_does_not_include_peer_outputs():
    assert hasattr(review,"make_prompt"), "phase-aware source prompt is missing"
    p=review.make_prompt("domain","initial","question",[material()],[],[])
    assert "measured at 23 C" in p
    with pytest.raises(ValueError):review.make_prompt("domain","initial","question",[material()],[{"secret":"peer answer"}],[])


def test_readable_answer_keeps_checked_answer_location_and_claim_kind():
    a=answer();a['findings'][0]['kind']='interpretation'
    a['answers']=[{'question_id':'critical-initial-q1','answer':'reported here','citations':[{'source_id':'S1','start_line':2,'end_line':2,'quote':'measured at 23 C'}],'status':'answered'}]
    text=review.readable_answer(a)
    assert '[해석]' in text
    assert '근거 S1 · 2–2줄: measured at 23 C' in text.split('[답변 critical-initial-q1]')[1]


def test_role_question_contract_is_part_of_answer_validation():
    a=answer()
    with pytest.raises(ValueError,match='peer_question'):review.validate_answer(a,[material()],'initial',[],role='domain')
    a['questions']=[{'id':'domain-initial-q1','to_role':'domain','question':'why','why_it_matters':'comparison'}]
    with pytest.raises(ValueError,match='routing'):review.validate_answer(a,[material()],'initial',[],role='domain')
    a['questions'][0]['to_role']='critical'
    review.validate_answer(a,[material()],'initial',[],role='domain')
