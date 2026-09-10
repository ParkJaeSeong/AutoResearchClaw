"""Publish audited coordinator follow-up, without altering reviewed inputs."""
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save
BASE=Path(__file__).resolve().parent
run=BASE/'selection-hypotheses-02'
audit=json.loads((run/'audit.json').read_text())
assert audit['answer_match'] and audit['phase_disclosure_checked'] and audit['new_submissions']==9
s=json.loads((BASE/'selection-reviewed-draft.json').read_text())
s['summary']='조건·계보 감사와 재검토 완료: 전체 EC925행은791개 고유 시료, PC/CNT137행은130개 고유 시료다. 공식 XLSX와 CSV 전수 대조는 수치 허용오차 내 불일치0셀이다. 세 역할이 새9개 제출을 완료하여 누적54개이며 모두 질문 구체화의 조건부 진행을 권고했다. 새 쟁점0개, 기존22개는 미해결이어서 다음 단계 통과 조건은 충족하지 않았다. PC/CNT는 감사 우선 사례로 유지하고 H1 성능 비교와 물리 실험은 보류한다. 실제 재검토는 아래 02 연구 질문→3차 개정→공개 대화에서 확인한다. 아래는 조정자의 후속 정리이며 검증된 가설이나 corpus 승인이 아니다.'
h1,h2,h3=s['hypotheses']
h1['statement']='시료·측정 계보를 확인한 PC/CNT에서 충전율에 조건 정보를 추가하면 새 문헌 예측에 실질적인 가치가 있는가?'
h1['test']='착수 전 목표값별 측정 이벤트·단위, 반복값 의미, 조건 실측/미상/가공 구분과 공동 조건 중첩을 확인한다. 같은 계보를 외부 분할 양쪽에 나누지 않는다. 동일 학습기와 내부 그룹 튜닝에서 문헌별 대응 MAE 차이를 비교하고, 문헌 가중치·최소 의미 개선폭·계보 단위 불확실성을 먼저 고정한다. 기준이 정해지기 전 성능 비교는 보류한다. 모집단 확대를 사후 성과 선택에 쓰지 않는다.'
h1['limits']='PC/CNT130시료 중6개는 기록된 모델 입력이 같은데 목표값이 다르다. 온도 상세값이 빈90행의 가공값은23이며, 로그 두께가 빈31행은 같은 가공 상수다. 가공 규칙·단위는 미확인이다. 문헌 내 변이 부재는 새 문헌 예측의 논리적 불가능을 뜻하지 않지만, 인과 효과와 평가 가능성을 보장하지도 않는다. PP/CNT도112행/82시료로 계보 문제가 남아 자동 대체하지 않는다.'
h2['statement']='동일 목적·정보·자원 상한에서 가설 선택이 판별 성과를 개선하며, 사전 목표 성과까지의 비용을 줄이는가?'
h2['test']='재검토 반론을 반영해 고정 예산의 오판·미판별률과 사전 성과 기준까지의 누적 비용을 별도로 평가한다. 실패·중단·미도달 캠페인을 포함한다. 분산과 연결성을 구분하고 복합 작용·모든 후보 불충분·판별 유보를 허용한다. 정량 예측이 갈리는 대조와 관측오차·독립 판정·중단 규칙을 먼저 정의한다. 단가 미정이면 자원량·시간·횟수로 보고한다.'
h3['test']='검사 전 동일 제안 집합과 검사 출력에서 독립된 판정 근거를 사용한다. 전체 제안 기준 비율과 실제 적합/부적합 집단별 오거절/통과율의 분모를 구분하고 판단 불가를 남긴다. 탐색 손실 허용치와 복구 성공 상태를 사전 고정한다. 계보 연결 정확도·지정 상태 복귀율·복구 시간·사람 개입을 함께 평가한다.'
s['unresolved']=[x for x in s['unresolved'] if not x.startswith('이번 협의에서 새 쟁점8개') and not x.startswith('추가 조건 감사는')]
s['unresolved']+=['원문 연결 후속: PC/CNT의 목표값 충돌6시료는 모두 rid44100, Takeda 등 Polymer2011, DOI10.1016/j.polymer.2011.06.046에 연결된다. 상세표는23[C]·10Hz·AC 전도도·그림4 추출을 기록하지만 가공표는 주파수 열이 없고 ac=0이다. 본문 접근403으로 그림4는 아직 미확인이다. 이 발견은 재검토 입력 동결 이후의 조정자 기록이다.',
 '공식 XLSX와 CSV의 일치는 파일 관계만 확인한다. 상세표는 시료당1행이므로 가공표의 여러 측정값 계보를 설명하지 못할 수 있다. 원자료는 삭제·평균·수정하지 않았다.',
 '재검토 후 기존22개 쟁점은 모두 열려 있다. 질문 설계에 대한 조건부 동의는 문제 해결 증거가 아니다.']
save(BASE/'selection-condition-draft.json',s)
save(BASE/'discovery-runs/restart-02/selection.json',s)
print('Published condition review coordinator draft')
