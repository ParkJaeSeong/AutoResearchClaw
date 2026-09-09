"""Continue only the approved synthetic acceptance case through native evidence."""
import json
from live_host import (BASE, ROOT, apply, council, envelope, head, host_review,
                       node_ref, ref, register, save, snap, uid)
from researchclaw.core.research_graph.m1_evidence import current_evidence, prepare_evidence_check
from researchclaw.core.research_graph.m1_search import corpus_status
from researchclaw.core.research_graph.m1_nodes import review_node

LIMIT = '제공된 합성 검사 자료이며 실제 문헌·실험이나 출처 진위를 인증하지 않는다.'
TEXTS = {
    'C1': '합성 전제 C1: 적용 조건의 전체 집계 평균이 비교 조건보다 개선되었다고 가정한다. 하위집단별 결과·표본 크기·불확실성은 제공되지 않았다.',
    'C2': '합성 전제 C2: 두 조건의 하위집단 구성 비율이 다르다고 가정한다. 집단 내 효과, 인과효과와 구성 효과의 크기는 제공되지 않았다.',
}


def check_evidence(artifact):
    node = artifact['node']
    project = head()['state']['project_id']
    checker = dict(id=uid(), project_id=project, actor_id=f'live-source-checker-{node}', role='owner', milestone='M1', active=True)
    resolver = dict(id=uid(), project_id=project, actor_id=f'live-source-resolver-{node}', role='resolver', milestone='M1', active=True)
    apply('m1.evidence.assign', {'setup_id': uid(), 'node_ref': node_ref(node),
                               'checker_assignment': checker, 'resolver_assignment': resolver})
    for _ in range(4):
        plans = prepare_evidence_check(snap(), node_id=node)['command_plans']
        if not plans:
            break
        apply(plans[0]['operation'], plans[0]['payload'])
    projection = current_evidence(snap())
    comparisons = []
    if node == 'collect':
        for source in artifact['content']['sources']:
            comparisons.append(dict(item_id=source['source_id'], source_ref=projection['collected_source_refs'][source['source_id']]['raw_ref'],
                                    locator='제공된 합성 전제 전체', span_start=0, span_end=len(source['raw_text']),
                                    access_level='full_text', observed_text=source['raw_text'], interpretation='제공된 합성 전제의 문자 일치 확인 대상'))
    else:
        for claim in artifact['content']['claims']:
            text = snap()['_issue_context']['objects'][claim['source_ref']['sha256']].decode()
            comparisons.append(dict(item_id=claim['claim_id'], source_ref=claim['source_ref'], locator=claim['locator'],
                                    span_start=claim['span_start'], span_end=claim['span_end'], access_level=claim['access_level'],
                                    observed_text=text[claim['span_start']:claim['span_end']], interpretation='공급 원문과 코드포인트 구간의 일치 확인 대상'))
    materials = {'node': artifact, 'comparisons': comparisons,
                 'source_texts': [{'ref': row['source_ref'], 'text': snap()['_issue_context']['objects'][row['source_ref']['sha256']].decode()}
                                  for row in comparisons]}
    packet = {'phase': 'final', 'node': node, 'purpose': '공급 원문·구간·인용의 문자 일치만 독립적으로 검사한다. 네트워크 출처 진위나 과학적 효과를 인증하지 않는다.',
              'input_binding': node_ref(node), 'isolation_level': 'instructions_only'}
    answer, host_id = host_review(f'{node}-source-check-{uid()}', 'methodology', packet, materials)
    if answer['recommendation'] not in ('ready', 'ready_with_limits') or answer['issues']:
        save(BASE / f'{node}-source-check-blocked.json', answer)
        raise RuntimeError('Independent source checker requested work; no supported result fabricated')
    check = prepare_evidence_check(snap(), node_id=node)
    observation = {**envelope(checker['actor_id']), 'verification_ref': check['verification_ref'], 'node_ref': check['node_ref'],
                   'checker_assignment_id': checker['id'], 'comparisons': comparisons,
                   'limitations': [LIMIT, f'실제 독립 검토 세션 {host_id}: {answer["rationale"]}']}
    apply('m1.evidence.observe', {'observation': observation})
    output = ref(observation)
    verification = head()['state']['verifications'][check['verification_ref']['artifact_id']]
    result = {**envelope(checker['actor_id']), 'verification_id': verification['id'], 'output_refs': [output],
              'outcome': 'supported', 'checked_scope': [verification['acceptance_rule']], 'limitations': [LIMIT, answer['rationale']]}
    apply('verification.result', {'verification_ref': check['verification_ref'], 'result': result})
    result_ref = ref(result)
    decision, resolver_host = host_review(f'{node}-source-resolution-{uid()}', 'critical', packet,
                                          {'verification': verification, 'result': result, 'observation': observation, 'source_materials': materials})
    if decision['recommendation'] not in ('ready', 'ready_with_limits') or decision['issues']:
        save(BASE / f'{node}-source-resolution-blocked.json', decision)
        raise RuntimeError('Independent resolver requested work; issue remains checking')
    event = {**envelope(resolver['actor_id']), 'issue_id': verification['issue_ids'][0], 'from_status': 'checking', 'to_status': 'resolved',
             'actor_assignment_id': resolver['id'], 'rationale': f'{decision["rationale"]} [実行 {resolver_host}]',
             'verification_refs': [result_ref], 'successor_ids': []}
    apply('issue.event', {'issue': None, 'event': event})
    save(BASE / f'{node}-status.json', prepare_evidence_check(snap(), node_id=node))
    print(json.dumps({'node': node, 'source_check': 'resolved', 'head_id': head()['id']}), flush=True)


if __name__ == '__main__':
    if head()['state'].get('m1_node_heads', {}).get('collect'):
        raise SystemExit('Existing collect preserved; inspect and resume explicitly.')
    screen = corpus_status(snap())
    # The entire project is a synthetic development test. This is a test-only
    # authority declaration, explicitly not an actual person's research approval.
    receipt_id = uid()
    apply('m1.corpus.decide', {'receipt_id': receipt_id, 'corpus_ref': screen['corpus_ref'], 'decision': 'approve',
                              'note': '합성 개발 수용 테스트용 승인 선언이다. 실제 사용자 문헌 승인·실험 허가가 아니다. 실제 연구에 재사용할 수 없다.'})
    receipt = head()['state']['approval_receipts'][receipt_id]
    apply('m1.corpus.bind', {'binding_id': uid(), 'event_id': uid(), 'receipt_ref': ref(receipt)})
    sources = [dict(source_id=name, access_status='full_text', access_url=f'https://example.invalid/synthetic-{name}',
                    accessed_at='2026-09-09T00:00:00Z', raw_text=text, origin_group_id='synthetic-case',
                    origin_description='동일한 개발 사례를 구성하는 두 전제. 독립 연구가 아니다.', limitations=[LIMIT])
               for name, text in TEXTS.items()]
    artifact = register('collect', {'sources': sources, 'limitations': [LIMIT]}, ('screen',))
    check_evidence(artifact)
    evidence = current_evidence(snap())
    claims = [dict(claim_id=name, source_id=name, source_ref=evidence['collected_source_refs'][name]['raw_ref'],
                   locator=f'합성 전제 {name} 전체', span_start=0, span_end=len(text), extracted_text=text,
                   access_level='full_text', interpretation='검토를 위해 제공된 전제이며 실측 결과가 아니다.', limitations=[LIMIT])
              for name, text in TEXTS.items()]
    artifact = register('extract', {'claims': claims, 'limitations': []}, ('screen', 'collect'))
    check_evidence(artifact)
    assert current_evidence(snap())['ready']
    print('Native evidence chain ready; inspect actual checks before synthesis.', flush=True)
