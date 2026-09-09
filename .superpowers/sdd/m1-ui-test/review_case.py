"""Native synthetic synthesis and deliberately contestable hypothesis for review."""
import json
from live_host import BASE, council, head, register, save, snap
from researchclaw.core.research_graph.m1_evidence import current_evidence
from researchclaw.core.research_graph.m1_nodes import review_node

LIMIT = '합성 전제의 논리 검토이며 실제 효과·유의성·인과효과가 검증되지 않았다.'

if __name__ == '__main__':
    evidence = current_evidence(snap())
    assert evidence['ready'], evidence['reason_codes']
    if head()['state'].get('m1_node_heads', {}).get('synthesize'):
        raise SystemExit('Existing synthesis preserved; resume explicitly after inspection.')
    refs = list(evidence['extraction_refs'].values())
    synthesis = {
        'findings': [dict(finding_id='F1', claim='제공된 C1은 집계 평균 개선을 가정하고 C2는 조건별 집단 구성 차이를 가정한다. 어느 전제도 각 집단 내 개선을 제공하지 않는다.',
                          evidence_refs=refs, counterevidence_refs=[], limitations=[LIMIT, '하위집단별 평균·가중치·표본 수·불확실성이 없다.'])],
        'rejected_alternatives': [dict(alternative_id='A1', description='집계 개선 자체가 모든 하위집단 내 개선을 입증한다.',
                                       reason='집계 평균은 집단별 평균과 구성비에 함께 의존한다. 주어진 두 전제에 집단별 방향이 없으므로 해당 일반화는 도출되지 않는다.', evidence_refs=refs)],
        'limitations': [LIMIT, '단일 합성 사례의 두 전제이며 독립적인 재현 연구 2개가 아니다.'],
    }
    artifact = register('synthesize', synthesis, ('screen', 'collect', 'extract'))
    council(artifact)
    status = review_node(snap(), 'synthesize')
    save(BASE / 'synthesize-status.json', status)
    if not status['ready']:
        raise SystemExit('Actual synthesis reviewers requested work; inspect before advancing.')
    hypothesis = {
        'hypotheses': [dict(hypothesis_id='H1', statement='집계 평균이 개선되었으므로 모든 하위집단에서도 개선이 입증되었다.',
                            population='조건에 포함된 모든 하위집단', prediction='모든 하위집단에서 평균이 개선된다.',
                            falsification_condition='전체 집계 평균이 개선되지 않으면 기각한다.', evidence_refs=refs,
                            alternative_ids=['A1'], limitations=[LIMIT])],
        'limitations': [LIMIT, '검토자의 교차 검증을 받는 초안이다. 이 문서의 주장은 승인된 결론이 아니다.'],
    }
    artifact = register('hypothesize', hypothesis, ('screen', 'extract', 'synthesize'))
    council(artifact)
    status = review_node(snap(), 'hypothesize')
    save(BASE / 'hypothesize-r1-status.json', status)
    print(json.dumps({'node': 'hypothesize', 'ready': status['ready'], 'reasons': status['reason_codes'],
                      'issues': status['unresolved_issue_ids']}, ensure_ascii=False), flush=True)
