"""Record the M1 review and issue its package; do not impersonate an M2 receiver."""
import json
from live_host import BASE, apply, council, envelope, head, node_ref, register, save, snap, uid
from researchclaw.core.research_graph.issues import _Inputs
from researchclaw.core.research_graph.gates import _status
from researchclaw.core.research_graph.m1_review import _owner, prepare_hypothesis_review
from researchclaw.core.research_graph.m1_nodes import review_node
from researchclaw.core.research_graph.work_accounting import work_sources, accounting_status
from researchclaw.core.research_graph.handoffs import handoff_status

if __name__ == '__main__':
    if head()['state'].get('m1_node_heads', {}).get('review'):
        raise SystemExit('Existing review preserved; inspect and resume explicitly.')
    inputs = _Inputs(snap())
    dispositions, questions = [], []
    for issue in inputs.state['issues'].values():
        status, event = _status(inputs, issue)
        owner = _owner(inputs, issue)
        dispositions.append(dict(issue_id=issue['id'], disposition='native_resolved' if status == 'resolved' else 'carry_forward',
                                 owner_assignment_id=owner, hypothesis_ids=['H1'],
                                 rationale='고정된 기존 해소 조건의 독립 검증 및 실제 해소 기록을 인용한다.' if status == 'resolved' else '선택적 해석 명확화 쟁점을 자동으로 지우지 않고 다음 검토에 보존한다.',
                                 verification_refs=event['verification_refs'] if status == 'resolved' else []))
        if status != 'resolved':
            questions.append(dict(issue_id=issue['id'], question=issue['question'], method='logic_check',
                                  resolution_condition=issue['resolution_condition'], owner_assignment_id=owner,
                                  to_milestone='M1', budget_ref=None,
                                  limitations=['선택적 표현 명확화 과제로 남긴다. 실험 실행이나 M2 이관 승인이 아니다.']))
    content = {'prior_issue_dispositions': dispositions, 'open_questions': questions,
               'limitations': ['합성 개발 수용 테스트이다. 실제 연구 문헌 승인이나 실험이 아니다.',
                               'H1은 미검증 가설이다. 논리적 정합성의 회복이 경험적 입증을 뜻하지 않는다.',
                               '선택적 쟁점은 열린 상태로 보존하며 모든 원문과 이전 가설 버전을 유지한다.']}
    artifact = register('review', content, ('screen', 'extract', 'synthesize', 'hypothesize'))
    council(artifact)
    status = prepare_hypothesis_review(snap())
    save(BASE / 'review-status.json', status)
    print(json.dumps({'review_ready': status['ready'], 'reasons': status['reason_codes']}, ensure_ascii=False), flush=True)
    if not status['ready']:
        raise SystemExit('Actual final review requires work; no handoff fabricated.')
    for source in work_sources(snap()):
        if not source['recorded']:
            apply('m1.work.record', {'record_id': uid(), 'source_kind': source['source_kind'], 'source_ref': source['source_ref']})
    apply('work_ledger.refresh', {'ledger_id': uid()})
    save(BASE / 'accounting-status.json', accounting_status(snap()))
    publication = envelope()
    apply('m1.handoff.issue', {'publication': publication, 'review_ref': node_ref('review')})
    status = handoff_status(snap(), handoff_id=publication['id'])
    save(BASE / 'handoff-status.json', status)
    print(json.dumps({'handoff_status': status['status'], 'gate_ready': status['gate_ready'],
                      'reasons': status['reason_codes'], 'head_id': head()['id']}, ensure_ascii=False), flush=True)
