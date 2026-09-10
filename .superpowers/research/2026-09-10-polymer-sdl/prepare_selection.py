"""Coordinator draft based on disclosed reports and local source-file inspection.
Does not submit native evidence, resolve an Issue, or manufacture consent.
"""
import csv
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save

BASE=Path(__file__).resolve().parent
RUN=BASE/'discovery-runs/restart-02'
sources=json.loads((RUN/'sources.json').read_text())
all_keys={s['key'] for s in sources}
groups=[
 dict(id='data',title='우선 검토 · 데이터와 평가 분할',
      reason='전기전도도 재현 평가를 먼저 준비한다. 저자 CSV를 직접 읽었으며 EC925행·TC292행이다. PC/CNT의 EC137행은 문헌ID16개에 걸친다. 최종CSV에서 expt 결측은 없지만 문헌/저자 그룹은 제조 배치가 아니며, 원입력 일부가 처리 과정에서 빠졌는지는 별도 감사가 필요하다.',
      source_keys=['doi:10.1021/acs.jcim.3c01894','url:https://github.com/shimakawa-hvg/expt-group-partitioning',
       'doi:10.1021/acs.macromol.2c02249','doi:10.1038/s43246-024-00731-w',
       'url:https://github.com/mathsphy/probing-ood']),
 dict(id='method',title='우선 검토 · 가설 판별과 공정한 비교',
      reason='가설 검증 에이전트의 추가 효과와 일반 최적화 성과를 구분한다. POPPER는 순차 반증 방법의 참고 자료이며 고분자 물리 실험의 성능 보장은 아니다. 적응적 자료 재사용과 모든 후보 가설이 틀린 경우의 처리 조건을 확인한다.',
      source_keys=['url:https://proceedings.mlr.press/v267/huang25n.html','url:https://github.com/snap-stanford/POPPER',
       'doi:10.1016/j.patter.2023.100704','url:https://arxiv.org/pdf/2605.06839',
       'doi:10.1002/mats.201800016','doi:10.1126/science.aaa9375',
       'doi:10.1038/s41524-021-00656-9']),
 dict(id='lab',title='우선 검토 · SDL 실행과 실패 처리',
      reason='제조–측정–다음 실험의 연결 및 사람 개입·실패·전체 비용을 검토한다. 박막과 3D프린팅 사례를 PC/CNT 혼합·성형·전도 측정으로 바로 일반화하지 않는다.',
      source_keys=['doi:10.1038/s41467-024-55655-3','doi:10.1039/d4mh00797b',
       'doi:10.1126/sciadv.aaz1708','doi:10.1038/s41467-024-48534-4',
       'doi:10.1038/s41467-024-45569-5','doi:10.1039/d5dd00337g']),
 dict(id='mechanism',title='추가 확인 · 경쟁 기전과 대체 소재',
      reason='계면·배향·접촉망·공극·결정화의 직접 관측과 통제 실험을 찾는다. 접근 실패/초록 수준 후보를 포함해 남기며 기전 입증으로 간주하지 않는다.',
      source_keys=['doi:10.1038/s41467-026-69872-5','doi:10.1016/j.compositesb.2026.113845',
       'doi:10.1021/acsnano.8b06290','doi:10.1021/acsami.8b16616',
       'doi:10.1039/d5na00373c']),
]
chosen={key for group in groups for key in group['source_keys']}
assert chosen <= all_keys, chosen-all_keys
groups.append(dict(id='remaining',title='보존 · 후속 선별 후보',
    reason='위 우선순위 밖의 자료도 삭제하지 않는다. DOI가 없는 URL, 같은 논문의 다른 버전, 저장소·데이터 자료가 별도 후보로 남아 있다. 197건은 고유 논문 수가 아니며 독립 근거 수로 합산하지 않는다.',
    source_keys=sorted(all_keys-chosen)))
selection=dict(status='draft',
 summary='조정자 초안: 197개 참고자료 후보 중23개 식별자 레코드를 우선 검토한다. 대표 예측 사례는 PC/CNT 전기전도도, 대안은 PP/CNT다. PC/CNT137행·16문헌ID, PP/CNT112행·14문헌ID를 확인했지만 실제 실험실·배치 독립성 및 원자료 이용 조건은 추가 확인해야 한다. 먼저 문헌 단위 예측 평가를 준비하고, 실제 장비와 구조 관측을 확인한 후 기전 판별 실험을 구체화한다. 에이전트의 합의·검증 완료 또는 사용자 승인 기록이 아니다.',
 groups=groups,
 hypotheses=[
  dict(id='H1',statement='PC/CNT에서 조성·충전율에 측정 조건을 더한 모델은 문헌을 분리한 예측 평가에서도 오차를 줄인다.',
       test='같은 학습기·튜닝 예산에서 조성 기반 입력과 온도·시편 두께·측정법을 추가한 입력을 비교한다. 주 지표 후보는 원자료 log10(EC) 척도의 문헌별 MAE다. rid/expt/expt_*는 분할·감사용이며 예측 입력에서 제외한다. 최종 평가 문헌은 검색·메모리 입력과 분리하고 공개자료 사전학습 오염 한계를 남긴다.',
       limits='효과 크기·합격 기준은 학습 전에 정해야 한다. 가공 CSV의 무결측은 실측 원자료의 완전성을 뜻하지 않는다. 조건 변수의 개선을 기전 인과효과로 해석하지 않는다.'),
  dict(id='H2',statement='가설별 구분 관측을 선택하는 에이전트는 동일 정보·계산·실험 예산의 비교군보다 경쟁 설명을 더 효율적으로 판별한다.',
       test='PC/CNT의 전도 변화에 대해 접촉망/분산 변화, 시편·측정 조건 차이를 경쟁 설명으로 둔다. 조성·온도·시편 형상을 통제하고 정량 분산/연결성 관측이 가능한지 먼저 확인한다. 동일 목적의 실험 선택, 무작위 선택, 가설 모듈 제거를 비교하며 판별 유보도 결과로 남긴다.',
       limits='현재 CSV의 전도도만으로 기전을 식별하거나 가설의 정답을 만들 수 없다. 장비와 추가 관측을 확보하기 전에는 물리 실험 설계 확정 및 수행을 보류한다.'),
  dict(id='H3',statement='시료 계보와 실행 전 검사를 연결한 SDL 제안은 유효한 탐색 범위를 유지하면서 부적합 제안과 추적 불가능한 결과를 줄인다.',
       test='배합–혼합–성형–전극/치수 확인–측정의 단계별 입력·품질·실패·재시도를 기록한다. 검사 포함/제외 구성에서 유효 제안 비율, 실패 비용, 사람 개입, 경과시간을 함께 비교한다.',
       limits='현재 PC/CNT 실험 장비가 있다는 가정은 하지 않는다. 박막 SDL의 처리량을 PC/CNT 공정의 성능으로 사용하지 않는다.'),
 ],
 unresolved=[
  'PC/CNT를 실제 제조·측정할 장비, 예산, 온도/농도/형상 범위는 미정이다.',
  '데이터의 전도도 단위·로그 변환·가공/대체 값·문헌 계보와 데이터별 사용권을 원자료와 대조해야 한다.',
  '가공 EC925행의 expt 결측은0이지만, 더 큰 sample_detail1599행에서 제외된 이유와 저자 그룹 분할의 타당성은 미해결이다.',
  '문헌·저자 그룹을 제조 배치 또는 독립 실험실로 간주하지 않는다. 예측 가능한 자료가 기전 판별 가능한 자료인 것은 아니다.',
  '초기197건은 DOI/URL 기준 식별자 중복 제거다. 논문–프리프린트–데이터–코드의 계보를 묶는 작업이 남았다.',
  '이 선정안은 원문 검증과 별개인 조정자 제안이다. native corpus 승인·검증·가설 노드는 아직 생성하지 않는다.',
 ])
assert len(chosen)==23
save(RUN/'selection.json',selection)
save(BASE/'selection-draft.json',selection)
print(json.dumps(dict(priority_records=len(chosen),retained_other_records=len(all_keys-chosen)),ensure_ascii=False))
