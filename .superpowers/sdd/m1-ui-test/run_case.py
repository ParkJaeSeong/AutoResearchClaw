"""Synthetic acceptance case authored by the coordinator; reviewers use live_host."""
import json
from live_host import BASE, ROOT, cli, council, head, register, save
from researchclaw.core.research_graph.m1_nodes import review_node
from live_host import snap

LIMIT = '합성 개발 검사 자료이며 실제 문헌·실험 결과가 아니다.'
SCOPE = {
    'user_goal': 'M1 개발 테스트: 제공된 합성 사례에서 집계 평균 개선을 모든 하위집단의 개선으로 일반화할 수 있는지 검토하고, 반론·가설 개정·재검토 이력을 확인한다.',
    'user_constraints': ['실제 연구 승인이 아닌 개발 테스트용 범위 선언이다.', 'M2 실험은 수행하지 않는다.', '제공된 두 합성 전제만 사용하고 외부 논문이나 수치를 만들어내지 않는다.'],
    'agent_assumptions': ['합성 전제 C1은 적용 조건의 집계 평균이 비교 조건보다 개선되었다는 가정이다.', 'C2는 두 조건의 하위집단 구성비가 다르다는 가정이다.', '집단별 결과·표본 크기·불확실성·무작위 배정 자료는 없다. 과학적 효과 입증이 아닌 논리 검토 대상이다.'],
}
QUESTIONS = {'questions': [
    {'question': '집계 평균 개선만으로 모든 하위집단의 개선을 논리적으로 도출할 수 있는가?', 'rationale': '집계 수준 주장과 집단 수준 주장을 구분한다.'},
    {'question': '집단 구성 효과와 집단 내 변화의 대안 설명을 구별하려면 어떤 정보가 추가로 필요한가?', 'rationale': '인과효과나 유의성을 주장하지 않고 후속 검증의 정보 공백을 명시한다.'}],
    'agent_assumptions': ['추가 수치는 만들지 않으며 미해결 실증 질문은 M2 후보로만 기록한다.']}
SEARCH = {'queries': ['합성 전제 집계 평균 구성비'], 'sources': ['제공된 합성 테스트 입력'],
          'inclusion_criteria': ['이 테스트에 명시적으로 제공된 C1 또는 C2 합성 전제'],
          'exclusion_criteria': ['제공되지 않은 실제 연구나 수치', '집계와 하위집단 관계에 무관한 자료']}
SCREEN = {
    'search_log': [{'search_id': 'provided-inputs', 'query': SEARCH['queries'][0], 'source': SEARCH['sources'][0],
                   'searched_at': '2026-09-09T00:00:00Z', 'result_count': 2}],
    'candidates': [dict(source_id=f'C{i}', title=f'합성 전제 C{i} · 실제 논문 아님', doi=None, arxiv_id=None,
                        url=f'https://example.invalid/synthetic-C{i}', source_type='synthetic-premise', access_status='full_text',
                        search_ids=['provided-inputs'], stance='unknown') for i in (1, 2)],
    'decisions': [dict(source_id=f'C{i}', decision='include', reason='제공된 논리 검토 전제 전체를 보존한다. 외부 검색 결과가 아니다.') for i in (1, 2)],
}


if __name__ == '__main__':
    if ROOT.exists():
        raise SystemExit('Existing acceptance project preserved. Resume explicitly after inspecting the stored state.')
    cli('init', ROOT, '--topic', '합성 사례 · 집계 개선과 하위집단 일반화', '--content-origin', 'synthetic')
    save(BASE / 'case-inputs.json', {'origin': 'synthetic', 'limitations': [LIMIT],
                                  'scope': SCOPE, 'questions': QUESTIONS, 'search': SEARCH, 'screen': SCREEN})
    for name, content, parents in (
        ('scope', SCOPE, ()), ('questions', QUESTIONS, ('scope',)),
        ('search', SEARCH, ('scope', 'questions')), ('screen', SCREEN, ('scope', 'questions', 'search'))):
        artifact = register(name, content, parents)
        council(artifact)
        status = review_node(snap(), name)
        save(BASE / f'{name}-status.json', status)
        print(json.dumps({'node': name, 'ready': status['ready'], 'reasons': status['reason_codes']}, ensure_ascii=False), flush=True)
        if not status['ready']:
            raise SystemExit('Native policy requires work; inspect actual reviewer output before continuing.')
