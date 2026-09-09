"""Revision authored after reading seven actual disclosed major objections."""
import json
from live_host import BASE, council, register, save, snap
from researchclaw.core.research_graph.m1_evidence import current_evidence
from researchclaw.core.research_graph.m1_nodes import review_node

refs = list(current_evidence(snap())['extraction_refs'].values())
content = {
    'hypotheses': [dict(
        hypothesis_id='H1',
        statement='미검증 가설: 동일한 기준으로 정의된 각 하위집단에서 적용 조건 A의 평균이 비교 조건 B보다 높다. C1·C2의 집계 개선만으로 이 보편 가설이 입증되거나 기각된 것은 아니다.',
        population='조건 A와 B에서 동일한 기준으로 정의할 하위집단. 집단 정의와 집단별 자료는 아직 제공되지 않아 특정 집단을 만들어내지 않는다.',
        prediction='개선 방향을 높은 평균으로 정한 동일 지표에서, 모든 하위집단 g의 조건 간 평균 차이 μ(A,g)−μ(B,g)가 양수이다. 이는 시간 변화나 인과효과의 주장이 아니다.',
        falsification_condition='동일하게 정의된 하위집단 중 하나라도 조건 간 평균 차이가 0 이하이면 보편 예측의 논리적 반례다. 실제 표본으로 판단하려면 집단별 평균·표본 수·불확실성·사전 판정 기준이 필요하며, 비유의성만으로 비개선을 확정하지 않는다. 구성비가 다를 때 집계 개선은 일부 집단의 미개선을 숨길 수 있고 집계 미개선도 모든 집단의 개선과 양립할 수 있어 집계 방향이 이 조건을 대신하지 않는다.',
        evidence_refs=refs, alternative_ids=[],
        limitations=[
            '합성 전제에 대한 미검증 가설이며 실제 관찰·실험 결과가 아니다.',
            'synthesize의 A1은 집계 개선으로 집단별 개선을 입증했다는 추론을 기각한 것이다. H1은 같은 입증 추론을 철회하고 검증 가능한 가능성만 남긴다. 따라서 A1을 경쟁 설명 ID로 잘못 연결하지 않는다.',
            '경쟁 설명으로 구성비 차이에 의한 집계 개선, 일부 집단만의 개선, 구성비와 집단별 차이의 동시 기여를 보존한다. 이들은 현재 전제로 배제되지 않았다.',
            '후속 구별에는 조건별 집단 평균·구성비 비교와 공통 가중치 표준화가 필요하다. 이는 검증 방향이며 실행된 분석이나 확정 실험 설계가 아니다. 표준화 비교만으로 인과효과가 식별되지는 않는다.',
        ])],
    'limitations': ['원문·표본이 없는 합성 개발 사례다.', '개정 자체는 쟁점 해결이 아니다. 기존 일곱 major 쟁점의 독립 검증과 해소 기록을 별도로 요구한다.'],
}
artifact = register('hypothesize', content, ('screen', 'extract', 'synthesize'),
                    reason='세 실제 검토자의 일곱 major 쟁점에 따라 입증 단정을 철회하고 집단별 반증 조건·경쟁 설명·A1 참조를 수정한다.')
council(artifact)
status = review_node(snap(), 'hypothesize')
save(BASE / 'hypothesize-r2-status.json', status)
print(json.dumps({'node': 'hypothesize', 'revision': 2, 'ready': status['ready'],
                  'reasons': status['reason_codes'], 'unresolved': status['unresolved_issue_ids']}, ensure_ascii=False), flush=True)
