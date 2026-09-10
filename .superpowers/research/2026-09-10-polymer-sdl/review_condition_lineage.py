"""Re-review a frozen condition audit and revised H1/H2/H3 protocol."""
import json
import review_selection_hypotheses as engine
import study_host as host
from researchclaw.core.research_graph.m1_nodes import review_node

BASE=host.BASE
RUN=BASE/'selection-hypotheses-02'


def main():
    RUN.mkdir(exist_ok=False)
    report=(host.REPO/'docs/research/2026-09-10-polymer-sdl/condition-lineage-review.md').read_text()
    audit=json.loads((BASE/'condition-lineage-audit.json').read_text())
    assert audit['all_processed_rows_matched']==925
    assert all(v['mismatched_cells']==0 for v in audit['xlsx_csv_comparison'].values())
    previous=json.loads((BASE/'selection-reviewed-draft.json').read_text())
    content={
      'questions':[
        {'question':'PC/CNT 자료의 원측정 계보와 조건 정보가 확인된 뒤, 충전율에 조건 정보를 추가하는 것이 새 문헌 예측에 실질적인 가치가 있는가?',
         'rationale':'현재는 평가 착수 보류다. 보고서의 H1 조건1–8을 충족하고 최소 개선폭·불확실성 규칙을 사전 고정한 뒤 비교한다. PC/CNT130개 고유 시료 중6개는 같은 기록 입력에서 목표값이 달라 측정 계보 확인이 우선이다. 조건의 인과 효과나 멀티 에이전트 효과로 확장하지 않는다.'},
        {'question':'구조·측정 조건의 단독 및 복합 작용과 판별 유보를 허용할 때, 동일 목적·정보·예산의 가설 선택이 판별 비용을 줄이는가?',
         'rationale':'보고서의 H2 관측 예측표를 검토한다. 아직 정량 예측 모델이나 실제 장비를 확보하지 않았다. 모든 후보 불충분, 오판·미판별·순차 중단과 전체 캠페인의 비용을 포함한다. 물리 검증은 보류한다.'},
        {'question':'독립 정답 명세가 있는 모의 제안 집합에서 실행 전 검사와 계보 연결이 부적합 통과를 줄이면서 유효 제안과 복구 가능성을 보존하는가?',
         'rationale':'보고서의 H3 독립 판정 기준을 검토한다. 전체 제안 기준 비율과 적합/부적합 집단별 오류율의 분모를 구분한다. 판단 불가를 별도 기록하며 실제 제조 성공률로 일반화하지 않는다.'},
      ],
      'agent_assumptions':[
        '우선23건과 PC/CNT는 감사·검토 대상으로 유지한다. corpus 승인·원문 검증·실험 실행 완료가 아니다. 기존 주요 쟁점은 해결된 것으로 변경하지 않는다.',
        '이번 개정은 이전 협의 이후 새로 동결한 감사 결과를 포함한다. 검토자는 제공된 집계를 평가하며 직접 원자료를 재검사했다고 주장하지 않는다.',
        report,
        '재현 가능한 파일 비교 및 조건 집계: '+json.dumps(audit,ensure_ascii=False),
        '우선 검토 출처와 선정 이유(새 원문 독해 아님): '+json.dumps(previous['groups'][:4],ensure_ascii=False),
        '확인된 사실과 미확인 원인을 분리한다. 빈 상세값에 특정 가공값이 연결된 사실만으로 대체 알고리즘이나 오류를 확정하지 않는다. 반복 목표값은 측정 계보를 확인하기 전 평균·삭제하지 않는다.',
        '현재 검토 대상은 질문과 후속 자료 확인 계획의 적절성이다. H1 성능 비교 착수·물리 실험은 보류한다. 제공된 중첩 지표는 주변 분포 진단이며 공동 중첩·독립성을 보장하지 않는다.',
      ]}
    host.save(RUN/'input.json',content)
    artifact=host.register('questions',content,('scope',),reason='조건·시료 계보 전수 대조와 공식 XLSX 일치 확인을 반영하고 H1 착수 조건·H2 관측표·H3 독립 판정을 재검토한다.')
    host.save(RUN/'artifact.json',artifact)
    engine.RUN=RUN
    host.host_review=engine.host_review
    issues=host.council(artifact)
    status=review_node(host.snap(),'questions')
    host.save(RUN/'status.json',status)
    print(json.dumps({'ready':status['ready'],'reason_codes':status['reason_codes'],'new_issues':len(issues)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
