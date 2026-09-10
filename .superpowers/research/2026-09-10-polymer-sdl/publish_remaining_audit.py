"""Publish a coordinator source reading without changing council decisions."""
import csv
import hashlib
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save

BASE = Path(__file__).resolve().parent
DATA = BASE / 'discovery-runs/restart-02/coordinator-audit'
DOC = BASE.parents[2] / 'docs/research/2026-09-10-polymer-sdl'

def main():
    prior = json.loads((BASE / 'target-pair-audit.json').read_text())
    for name, digest in prior['source_sha256'].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest
    details = [r for r in csv.DictReader((DATA / 'sample_detail_EC.csv').open()) if r['Sample ID'].startswith('42969-')]
    assert len(details) == 25
    assert all(not r['[elecon] temp'].strip() for r in details)
    evidence = {
        'rid': '42969', 'status': 'partial_full_text_checked',
        'reviewer': 'coordinator; not a new agent council or issue resolution',
        'doi': '10.1016/j.polymer.2009.12.041',
        'url': 'https://nrc-publications.canada.ca/eng/view/accepted/?id=a3d207d2-7f7c-4576-b46b-57a9a213c1c7',
        'pdf_sha256': hashlib.sha256((DATA / 'abbasi-2010.pdf').read_bytes()).hexdigest(),
        'inspected': 'PDF page 4 / printed page 924, section 2.6; text extracted and page visually inspected',
        'findings': [
            '측정 절은 두께 방향 DC 저항과 2탐침 장치를 설명한다.',
            '기술된 인가 전압은 순수 PC 및 1 wt% 이하 1000 V, 2 wt% 이상 100 V이며, 2 wt% 초과에서는 별도 장비의 I–V 곡선으로 저항을 구한다.',
            '120°C는 측정 전 최소 4시간 건조 조건이다. 전기 측정 온도로 사용할 수 없다.',
            '확인한 전기 측정 절에는 23°C가 명시되지 않았다. 인접 기계 시험 절의 실온을 전기 측정 조건으로 옮기지 않는다.'
        ],
        'linked_rows': 25,
        'detail_figure_references': sorted({r['[elecon] remarks'] for r in details}),
        'detail_methods': sorted({r['[elecon] method'] for r in details}),
        'unresolved': ['그림12의 공정별 곡선과 25행 각각의 시료·두께·측정 장비 대응', '가공표 23°C의 생성 근거', '상세표 I–V 표기의 적용 범위와 원문 장비 전환 조건의 일치'],
        'source_data_modified': False, 'native_issues_resolved': False
    }
    save(BASE / 'abbasi-source-reading.json', evidence)
    queue = json.loads((BASE / 'remaining-source-audit.json').read_text())
    # Keep triage reproducible; reviewed status is derived in this separate published snapshot.
    queue['source_readings'] = [evidence]
    for source in queue['sources']:
        if source['rid'] == '42969':
            source['status'] = evidence['status']
    save(BASE / 'remaining-source-reviewed.json', queue)
    text = ['# 재개 후 공개 원문 확인', '',
        '접근이 막힌 rid44100을 기다리는 동안 나머지 15문헌·123행의 감사 우선표를 만들고, 우선순위 첫 문헌 Abbasi 등(2010)의 공개 원문을 확보했다. 조정자의 자료 확인이며 새로운 에이전트 협의 결과는 아니다.', '',
        '[문헌별 우선표](remaining-source-audit.md) · [NRC 공개 원문](' + evidence['url'] + ')', '',
        '## 확인 범위', '', evidence['inspected'], '',
        *['- ' + item for item in evidence['findings']], '',
        '상세표의 해당 25행은 측정 온도가 비어 있고 추출 위치는 그림12, 측정법은 I–V curve로 기록돼 있다. 원문의 장비·전압 전환 조건을 각 행에 적용하려면 곡선과 공정별 시료를 추가 대조해야 한다.', '',
        '## 다음 확인', '', *['- ' + item for item in evidence['unresolved']], '',
        '원본 데이터의 해시는 이전 감사와 동일하다. 기존 협의 54개 제출·22개 열린 쟁점은 유지하며 문헌 선정 승인이나 M1 완료로 처리하지 않았다. 원문 접근이 막힌 rid44100 그림4도 계속 미확인이다.', '']
    (DOC / 'resumed-source-review.md').write_text('\n'.join(text))
    s = json.loads((BASE / 'selection-target-pair-draft.json').read_text())
    s['summary'] = '자료 확인 재개: 남은 PC/CNT 15문헌·123행의 감사 우선표를 만들고 Abbasi2010 공개 원문의 측정 절을 확인했다. DC 측정과 농도별 전압·장비 조건을 확인했지만 가공값 23°C의 근거와 25행의 그림12 곡선 대응은 미해결이다. rid44100 그림4는 출판사 사람 확인 대기다. 이번 추가 확인은 조정자 기록이며 기존 에이전트 협의 누적54개 제출·22개 열린 쟁점은 유지한다.'
    s['unresolved'] += ['Abbasi2010: 측정 절의 120°C는 사전 건조 조건이며 전기 측정 온도가 아니다. 상세표 25행의 온도 공백과 가공값 23°C 생성 근거는 미해결이다. 그림12·공정·시료·장비별 행 대응을 다음 확인한다. 공개 원문: ' + evidence['url']]
    save(BASE / 'selection-resumed-draft.json', s)
    save(BASE / 'discovery-runs/restart-02/selection.json', s)
    print('Published partial source reading; source hashes verified; council unchanged.')

if __name__ == '__main__':
    main()
