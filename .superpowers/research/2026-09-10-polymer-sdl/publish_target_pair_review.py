"""Expose partial primary-source tracing and a non-destructive hold proposal."""
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save
BASE=Path(__file__).resolve().parent
pairs=json.loads((BASE/'target-pair-audit.json').read_text())
s=json.loads((BASE/'selection-condition-draft.json').read_text())
s['summary']='원문·측정값 후속 대조: PC/CNT의 서로 다른 목표값6쌍과 완전 중복1쌍은 모두 rid44100에 연결된다. 시료별 CSV 행 번호·상세표 대응을 확인했다. 출판사 검색 발췌는 그림4를 AC 전도도–주파수 그래프로 설명하지만 그림 자체는 미확인이다. 출판사 본문은 사람 확인(CAPTCHA) 대기이며 주파수별 값 대응을 확정하지 않았다. 해당 문헌14행의 평가 전 보류 목록을 만들었고 원본은 변경하지 않았다. 앞선 질문3차 협의는 완료(누적54개 제출), 기존22개 쟁점은 미해결이다.'
s['hypotheses'][0]['limits']+=' 후속 대조에서7시료14행은 모두 같은 문헌으로 연결됐다. 보류 목록 적용 가정 시123행·123시료·15문헌·11저자 그룹이 남지만, 남은 자료의 사용 적합성도 검증되지 않았다.'
s['unresolved']=[x for x in s['unresolved'] if not x.startswith('원문 연결 후속:')]
s['unresolved']+=[
 '부분 원문 확인: 출판사 검색 발췌는 그림4가 충전율별 AC 전도도–주파수 그래프라고 설명한다. 상세표는10Hz와 그림4 추출을 기록하지만 가공표의 ac=0은 AC 부재로 해석할 수 없다. 각 목표값의 주파수·곡선·시편·추출 좌표는 미확인이다.',
 '확인할 원문: https://www.sciencedirect.com/science/article/pii/S0032386111005350 — 일반 크롬에서도 사람 확인(CAPTCHA)이 필요하다. 그림4·캡션·측정 본문 또는 저자 추출 계보 확보 전 원인을 확정하지 않는다.',
 '보류 대상 CSV 행: '+', '.join(map(str,pairs['non_destructive_hold_manifest']['csv_lines']))+'. 원본 필터·삭제·평균·값 선택을 수행하지 않았다. 상세표와 일치하는 값만 정답으로 고르지 않는다.'
]
save(BASE/'selection-target-pair-draft.json',s)
save(BASE/'discovery-runs/restart-02/selection.json',s)
print('Published partial tracing; full figure and native Issue resolution remain pending.')
