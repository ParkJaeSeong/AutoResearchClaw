"""Bind an existing scientific question to a durable Atlas request."""
from researchclaw.core.research_graph.views import build_view
from .atlas_client import AtlasError
from .atlas_session import _text
from .atlas_request_episode import RequestEpisode


def ask_research_question(session, key, question_id, previous=None):
    for value in (key, question_id):
        _text(value)
    if previous is not None:
        _text(previous)
    # Retry the original scientific context, even if later graph records exist.
    try:
        row = session._get(key)
    except AtlasError as exc:
        if str(exc) != 'atlas_request_unknown':
            raise
    else:
        if (not row.get('research_context') or row['question_id'] != question_id
                or row['previous'] != previous):
            raise AtlasError('atlas_request_conflict')
        episode = RequestEpisode.existing(session, key)
        try:
            result = session.poll(key)
        except Exception:
            if episode:
                episode.error()
            raise
        if episode:
            episode.accepted(result)
        return result
    view = build_view(session.root)
    selected = next((r for r in view['external_questions'] if r['record']['id'] == question_id), None)
    if selected is None:
        raise AtlasError('atlas_question_unknown')
    question = selected['record']
    decision = next(r['record'] for r in view['external_decisions']
                    if r['record']['id'] == question['decision_ref']['artifact_id'])
    context = dict(question_ref=selected['ref'], question=question,
                   decision=decision, selected_head=view['head_id'])
    text = (f"확인할 연구 질문: {question['question']}\n"
            f"이 질문이 나온 기존 결정: {decision['conclusion']}\n"
            f"현재 결정의 한계: {'; '.join(decision['limitations'])}\n"
            f"부족한 근거: {question['missing_evidence']}\n"
            f"답변이 바꿀 판단: {question['decision_impact']}\n"
            f"조회 범위: {question['scope']}\n"
            "보유 자료에서 확인한 저자 보고·Atlas 해석·미확인을 구분해 답하세요. "
            "수치·측정 배치·방향의 원문 위치와 출처 버전을 연결하세요. "
            "보유하지 않은 자료는 미확인으로 남기고 필요한 자료를 구체적으로 알려주세요. "
            "자료실에서 못 찾았다는 사실을 연구 가설의 반증으로 취급하지 마세요.")
    episode = RequestEpisode.start(session, key, context, previous)
    try:
        result = session.ask(key, text, question_id, previous, research_context=context)
    except Exception:
        episode.error()
        raise
    episode.accepted(result)
    return result
