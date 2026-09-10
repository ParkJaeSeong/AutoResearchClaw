"""Publish a coordinator revision, preserving the council's reviewed input."""
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save
BASE=Path(__file__).resolve().parent
run=BASE/'selection-hypotheses-01'
audit=json.loads((run/'audit.json').read_text())
assert audit['answer_match'] and audit['new_submissions']==9
selection=json.loads((BASE/'selection-draft.json').read_text())
selection['summary']='교차 검토 후 조정자 수정 초안: 세 역할이 독립 의견→상호 반박→최종 판단의9개 제출을 완료했다. 모두 연구 질문 구체화에 한정해 ready_with_limits로 판단했으나, 주요 쟁점이 열려 있어 시스템의 다음 단계 진행 조건은 충족되지 않았다. PC/CNT와 우선23건은 잠정 유지한다. H1은 예측 비교 가능성 확인, H2는 복합 기전·판별 유보, H3는 유효 제안 오거절 평가를 보강했다. 아래 수정 문구는 조정자 정리이며 재심 완료가 아니다. 실제 대화는 아래 M1 작업 지도에서 02 연구 질문→2차 개정→공개 대화로 확인한다.'
h1,h2,h3=selection['hypotheses']
h1.update(statement='PC/CNT에서 충전율 기준선에 측정 조건을 추가하는 것이 새로운 문헌의 예측에 도움이 되는지 평가할 수 있는가?',
 test='먼저 PC/CNT·PP/CNT·전체 EC의 실제 조건 열과 원자료 계보, 문헌 안팎 변이·충전율 중첩·학습/평가 지원 범위를 비교한다. 평가가 가능하면 같은 외부 문헌 분할에서 충전율 기준선과 조건 추가 모델의 대응 MAE 차이를 비교한다. 문헌 가중치·최소 개선폭·계보 단위 불확실성을 학습 전에 고정하고 전처리·튜닝은 내부 분할에서 수행한다. rid/expt/expt_*는 예측 입력에서 제외한다.',
 limits='검토 입력 동결 후 조정자가 추가 집계: PC/CNT137행에서 온도와 측정법은 문헌 내 변이가0/16, log10(thickness)는2/16이다. 이 추가 집계는 이번 에이전트 협의에서 검증하지 않았다. 문헌 내 변이 부재만으로 문헌 간 예측 비교가 불가능한 것은 아니지만 조건 자체의 인과 효과는 주장할 수 없다. 전체 소재에서만 평가 가능하면 별도 모집단 가설로 개정한다. 에이전트 자체의 효과 검정과도 구분한다.')
h2.update(statement='복합 작용과 판별 유보를 허용하는 가설 선택 에이전트는 동일 목적·정보·예산에서 오류 기준을 만족하는 판별의 비용을 줄이는가?',
 test='분산→연결성→전도도 경로와 측정 조건의 단독·복합 작용, 모든 후보 불충분을 관측 예측표로 정의한다. 구조 관측과 전기 측정의 시편 대응을 확인한다. 동일 목적 비교군·가설 모듈 제거와 비교하며 전체 캠페인의 누적 비용, 오판률, 예산 내 미판별률과 순차 중단 규칙을 사전 고정한다.',
 limits='분산 이미지 하나나 최종 전도도만으로 접촉망 또는 기전 정답을 만들지 않는다. 직접 관측과 장비가 미확정이므로 물리적 가설 판별 검증은 보류한다.')
h3.update(statement='실행 전 검사와 시료 계보가 유효한 제안을 과도하게 거절하지 않으면서 부적합 통과와 추적 실패를 줄이는가?',
 test='검사 전 동일 제안 집합 전체를 분모로 삼고 검사와 독립된 유효성 기준으로 부적합 통과율·유효 제안 오거절률·탐색 범위 보존을 비교한다. 원료–배치–시편–측정 연결의 정확성과 복구 가능성, 거절·실패·재시도·사람 개입·시간·비용을 함께 기록한다.',
 limits='장비 미정에서는 명시적 가상 제약하의 모의 실행·기록 재생 평가 설계로 한정한다. 실제 제조 성공률로 일반화하지 않는다.')
selection['unresolved']+=['이번 협의에서 새 쟁점8개가 등록되어 전체22개가 열려 있다. 반복 제기는 원문 보존 때문에 별도 기록하며 독립 문제8종으로 세지 않는다.',
 '세 역할은 질문 구체화의 조건부 진행을 권고했지만 major 쟁점은 현재 정책에서 진행을 막는다. 쟁점 해결 증거와 적절한 상태 전이가 필요하며 동의만으로 해소하지 않는다.',
 '추가 조건 감사는 가공 CSV 집계다. 원측정·대체 값·측정법0의 의미와 출처 매핑은 미확인이다.']
save(BASE/'selection-reviewed-draft.json',selection)
save(BASE/'discovery-runs/restart-02/selection.json',selection)
print('Published reviewed coordinator draft; native council preserved at '+audit['head_id'])
