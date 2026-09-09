"""Record the five-paper feasibility shortlist; never manufacture corpus consent."""
import json
from study_host import BASE, council, head, register, save, snap
from review_search import SEARCH
from researchclaw.core.research_graph.m1_search import prepare_search_council

# UTC lookup completion time, not publication date or an exhaustive search timestamp.
LOOKED_UP = '2026-09-09T16:27:53Z'
ROWS = [
    ('P01', 'Prevention of Leakage in Machine Learning Prediction for Polymer Composite Properties',
     '10.1021/acs.jcim.3c01894', None, 'https://pubmed.ncbi.nlm.nih.gov/38642039/', 'abstract', 'oppose',
     '무작위 분할의 성능 과대평가를 지적하는 반대·제약 근거로 보존. 전기전도도 데이터 감사의 우선 후보다. 공식 Figshare API /v2/articles/25657025에서 ci3c01894_si_002.xlsx, 453057 bytes, CC BY-NC 4.0과 다운로드 URL을 확인했다. 파일 내용·그룹 식별자·반복·측정 조건은 아직 검사하지 않았고 논문 전문은 접근 실패했다. 사용 가능 벤치마크 확정이나 특정 수지·필러 선택은 아니다.'),
    ('P04', 'Thermal conductivity modeling beyond the dilute limit using a body-centered cubic framework for densely packed polymer composites',
     '10.1038/s41467-025-67013-y', None, 'https://www.nature.com/articles/s41467-025-67013-y', 'full_text', 'unknown',
     '출판사 페이지의 초록·본문 일부를 확인한 열전도도 물리 모델 비교 후보. 구형에 가까운 필러의 체적분율·크기·계면 열저항을 다룬다. 전문 페이지 접근 가능과 전문 전체 검증은 다르다. 후속 재접근 일부는 차단됐다. 보충 데이터의 실제 열·문헌 그룹·단위·사용권·계면 열저항의 직접 측정/목표값 적합 여부는 미확인. 목표값으로 추정한 변수를 예측 입력으로 사용하지 않도록 감사 후 판단한다.'),
    ('P05', 'Machine learning guided resolution of mechanical trade-off in polymer composites via stress adaptive interface',
     '10.1038/s41467-026-69872-5', None, 'https://www.nature.com/articles/s41467-026-69872-5', 'full_text', 'unknown',
     '출판사 초록·서론·결과 일부에서 계면 설계와 Pareto/능동학습 결합을 확인했다. 기계 물성의 경쟁 설명·다목적 비교 후보로 포함한다. 전문 전체와 첨부 데이터 내용·사용권·배치/반복 기록은 미검증. 실제 장비·제조 가능성은 미확정이고 저자 보고 성능을 우리 방법의 개선 증거로 사용하지 않는다.'),
    ('P03', 'Autonomous platform for solution processing of electronic polymers',
     '10.1038/s41467-024-55655-3', None, 'https://www.nature.com/articles/s41467-024-55655-3', 'full_text', 'neutral',
     '출판사 초록·서론·자동화 공정 결과 일부를 확인했다. 용액 조제·코팅·후처리·전기 측정 SDL 연결의 참고 자료다. 고체 충전 복합소재 성형·기계시험 자동화의 직접 증거는 아니다. 장비 인터페이스, 실패 처리, 원자료·코드 사용권은 추가 확인하며 저자 처리량을 우리 실험실의 성능으로 가정하지 않는다.'),
    ('P02', 'Polymer Composites Informatics for Flammability, Thermal, Mechanical and Electrical Property Predictions',
     '10.1039/D4PY01417K', '2412.08407', 'https://arxiv.org/abs/2412.08407', 'abstract', 'neutral',
     'arXiv 초록과 저널 참조를 확인했다. 복합소재 표현과 다중 물성 예측의 배경 자료로 포함한다. 원자료 공개·사용권·평가 분할은 미확인이고 상용 데이터가 공개됐다고 가정하지 않는다.'),
]
SCREEN = {
    'search_log': [dict(search_id=f'lookup-{i+1}', query=query, source=SEARCH['sources'][0],
                        searched_at=LOOKED_UP, result_count=1)
                   for i, query in enumerate(SEARCH['queries'])],
    'candidates': [dict(source_id=row[0], title=row[1], doi=row[2], arxiv_id=row[3],
                        url=row[4], source_type='research_article', access_status=row[5],
                        search_ids=[f'lookup-{i+1}'], stance=row[6]) for i, row in enumerate(ROWS)],
    'decisions': [dict(source_id=row[0], decision='include', reason=row[7] +
                      ' 초기5편의 표적 조회로 선정한 자료이며 포괄성·신규성·가설 타당성 검증 완료를 뜻하지 않는다. 대표 소재 확정은 데이터 내용 감사 후 별도 결정한다.') for row in ROWS],
}

if __name__ == '__main__':
    if 'screen' in head()['state'].get('m1_node_heads', {}):
        raise SystemExit('Existing screen preserved; inspect and revise explicitly.')
    assert prepare_search_council(snap(), node_id='search')['ready']
    save(BASE / 'screen-input.json', SCREEN)
    artifact = register('screen', SCREEN, ('scope', 'questions', 'search'))
    council(artifact)
    status = prepare_search_council(snap(), node_id='screen')
    save(BASE / 'screen-status.json', status)
    print(json.dumps({'review_ready': status['review_ready'], 'approved': status['approved'],
                      'reasons': status['reason_codes']}, ensure_ascii=False), flush=True)
