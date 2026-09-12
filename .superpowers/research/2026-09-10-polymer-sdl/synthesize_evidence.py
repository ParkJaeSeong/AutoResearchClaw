"""Build a coordinator synthesis from preserved reviews; no stage approval or LLM call."""
import hashlib
import json
from pathlib import Path
from researchclaw.codex.source_review import validate_answer

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[2]
RUN=BASE/'source-analysis-01'
OUT=REPO/'docs/research/2026-09-10-polymer-sdl'


def build():
    materials=json.loads((RUN/'materials.json').read_text())
    receipt_path=OUT/'source-analysis-receipt.json'
    receipt=json.loads(receipt_path.read_text())
    reviews={r:json.loads((RUN/f'final-{r}/verified-answer.json').read_text()) for r in ('domain','methodology','critical')}
    for role,record in reviews.items():
        inbound=[q for r in reviews for q in json.loads((RUN/f'response-{r}/verified-answer.json').read_text())['answer']['questions'] if q['to_role']==role]
        validate_answer(record['answer'],materials,'final',inbound,role=role)
        assert record['material_hashes']=={m['id']:hashlib.sha256(m['text'].encode()).hexdigest() for m in materials}
        assert any(s['phase']=='final' and s['role']==role and s['host_id']==record['host_id'] for s in receipt['submissions'])
    # Each row records a use-specific coordinator judgment, not a vote or new experiment.
    rows=[
      dict(id='C01',title='같은 CNT 함량에서 제조·형상 조합 비교',finding_indexes=[0,1,6],
        conclusion='같은 함량에서 다섯 제조·형상 조합의 저장값과 순위를 잠정 비교할 수 있다.',
        allowed_use='조건을 맞춘 비교표 작성, 설명할 차이와 경쟁 가설 찾기',
        held_use='공정 하나의 인과 효과, 독립 반복 25회에 근거한 유의성 주장',
        challenge='공정·형상·두께·열이력이 함께 달라 개별 요인의 효과가 분리되지 않는다.',
        next_question='시편 형상과 측정 방향을 같게 해도 제조 조건에 따른 차이가 남는가?',
        recheck_trigger='정량 차이 또는 비율을 확정할 때만 해당 그림 점의 판독 오차를 확인한다.'),
      dict(id='C02',title='최종 두께와 시편 치수',finding_indexes=[1,2],
        conclusion='사출압축의 1.2 mm는 확인된 최종 시편 두께로 사용할 수 없다.',
        allowed_use='치수 출처의 불확실성을 표시하고 두께를 맞추는 대조 조건 설계',
        held_use='1.2 mm로 전도도 재계산, 1 mm로 자동 교정, 인장 구간 길이를 전극 간 거리로 사용',
        challenge='원문의 금형 간격·명목 시편 치수와 전기 측정 치수는 같은 값이라고 보장되지 않는다.',
        next_question='동일한 최종 두께와 전극 배치를 갖는 시편을 어떻게 확보할 것인가?',
        recheck_trigger='기존 치수를 수치 보정이나 정량 설명변수로 사용하려 할 때 실측·최종 치수 기록을 요청한다.'),
      dict(id='C03',title='측정 온도와 장비·방법',finding_indexes=[3],
        conclusion='23°C와 방법 지시자 0을 검증된 측정 조건으로 간주하지 않는다.',
        allowed_use='실측·미상·가공 입력을 구별하는 조건표와 일관된 측정 절차 설계',
        held_use='현재 25행으로 온도·장비·측정법 각각의 효과 추정',
        challenge='온도 공란과 처리 값이 다르며, 일부 함량에서 장비도 전환된다. 측정 차이가 실제 원인이라는 증거는 아니다.',
        next_question='같은 시편을 같은 온도·방향·전극 조건에서 측정하면 조합 간 차이가 유지되는가?',
        recheck_trigger='기존 기록을 측정 조건 비교에 투입할 때 해당 열의 생성 규칙과 측정 기록을 요청한다.'),
      dict(id='C04',title='전도도 단위와 CNT 함량',finding_indexes=[0,4],
        conclusion='논문 내부에서는 wt%와 S/cm 축을 기준으로 읽되, 통합 CSV의 단위·환산 정확성을 확정하지 않는다.',
        allowed_use='원문 단위를 명시한 사례별 정리와 같은 함량의 잠정 비교',
        held_use='여러 문헌의 절대 전도도 통합, 검증되지 않은 체적분율 환산',
        challenge='CSV 두 파일의 로그값 일치는 단위나 밀도 환산이 옳다는 증거가 아니다.',
        next_question='후속 비교에서 질량분율과 전도도 단위를 어떻게 일관되게 기록할 것인가?',
        recheck_trigger='문헌 간 수치 통합 전에 해당 단위 정의·밀도·환산식을 확인한다.'),
      dict(id='C05',title='CNT 함량과 PC 원료 구성',finding_indexes=[5],
        conclusion='함량 변화에는 마스터배치 유래 PC 비율 변화도 동반될 수 있다.',
        allowed_use='CNT 증가와 PC 구성 변화의 설명을 구별할 대조 설계',
        held_use='함량 추세를 CNT 증가만의 효과로 단정',
        challenge='두 PC가 같다는 근거가 부족하다. 이 설명은 같은 함량 내 제조 조합 차이를 단독으로 설명하지 않는다.',
        next_question='PC 공급원을 고정하거나 PC 혼합비를 별도로 바꿨을 때 같은 추세가 나타나는가?',
        recheck_trigger='함량 효과를 CNT의 단독 효과로 해석하려 할 때 PC 등급·분자량·혼합비 근거를 요청한다.'),
      dict(id='C06',title='137행의 문헌 간 통합 비교',finding_indexes=[7],
        conclusion='137행은 확보한 사례 분포와 비교 가능한 부분집합을 찾는 데 사용한다.',
        allowed_use='문헌별 조건·자료 의존성·누락 정보를 정리하고 평가 대상 후보 선정',
        held_use='전체 PC/CNT에 대한 일반화, 동일 ID의 임의 평균·삭제, expt를 독립 배치로 취급',
        challenge='같은 ID에 복수 값이 있고, 온도 기록과 저자 그룹은 문헌 차이를 반영할 수 있다.',
        next_question='새 문헌으로의 예측을 평가할 때 어떤 원자료·저자 연결을 같은 그룹으로 묶어야 하는가?',
        recheck_trigger='평가 데이터 분할을 확정하기 전에 사용할 문헌의 측정 사건과 데이터 재사용 관계를 확인한다.'),
    ]
    for row in rows:
        row['disposition']='limited_use'
        row['basis']=[reviews['domain']['answer']['findings'][i] for i in row.pop('finding_indexes')]
        for f in row['basis']:
            for c in f['citations']:
                m=next(m for m in materials if m['id']==c['source_id'])
                assert c['quote'] in '\n'.join(m['text'].splitlines()[c['start_line']-1:c['end_line']])
                c['source_ref']=m['ref']
    return dict(schema_version=1,kind='coordinator_evidence_synthesis',conceptual_stage=6,status='draft',
      topic='PC/CNT 전도도 자료의 사용 범위와 후속 가설',knowledge_iteration='5단계는 현재 자료 기준 이번 회차 마감; 모든 문헌의 독해 완료를 뜻하지 않음',
      source_council_id=receipt['council_id'],input_head_id=receipt['head_id'],
      source_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
      prior_final_reviews=[s for s in receipt['submissions'] if s['phase']=='final'],
      authorship='Pilot 조정자가 기존 3역할의 최종 검토를 종합함. 이번 작성에서 새 에이전트 발언이나 실험 결과를 생성하지 않음.',
      new_searches=0,new_host_submissions=0,resolved_issue_ids=[],native_stage_completed=False,
      rows=rows,next_focus_proposal='C01·C03·C05를 H2의 경쟁 설명 판별 사례 후보로 구체화한다. H1의 평가 대상·분할 명세는 별도로 준비한다. H2를 주가설로 선택했거나 H1–H3의 에이전트 효과를 입증한 것은 아니다.',
      native_registration_gap='기존 synthesize 등록은 승인된 선정안과 collect/extract 근거 검토를 요구한다. 이번 회차 마감 선언을 그 검사의 통과로 바꾸지 않는다. 이 산출물은 근거 종합 초안이며 기존 노드 상태를 변경하지 않는다.')

if __name__=='__main__':
    value=build()
    target=OUT/'stage6-synthesis.json'
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('6 use-specific judgments; source spans and three prior final hosts checked.')
