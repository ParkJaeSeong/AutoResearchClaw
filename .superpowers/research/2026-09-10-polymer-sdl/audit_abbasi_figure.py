"""Trace Fig.12 process groups to author rows; do not redigitize or repair data."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from researchclaw.codex.literature_loop import save

BASE = Path(__file__).resolve().parent
DATA = BASE / 'discovery-runs/restart-02/coordinator-audit'
DOC = BASE.parents[2] / 'docs/research/2026-09-10-polymer-sdl'
# Visual inspection of printed p.932 Fig.12, checked against pp.923-924 §2.2.
GROUPS = {
    '1': ('Compression (disk)', 'filled circle', '[proc] Compression', 1.5),
    '2': ('Microinjection-compression (disk)', 'open hexagon', '[proc] Microinjection-compression', 1.2),
    '3': ('Microinjection (disk)', 'filled downward triangle', '[proc] Microinjection', 1.0),
    '4': ('Conventional injection (dog-bone)', 'open square', '[proc] Injection', 4.0),
    '5': ('Microinjection (dog-bone)', 'star', '[proc] Microinjection', 0.78),
}

def main():
    previous = json.loads((BASE / 'target-pair-audit.json').read_text())
    for name, digest in previous['source_sha256'].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest
    source = json.loads((BASE / 'abbasi-source-reading.json').read_text())
    assert hashlib.sha256((DATA / 'abbasi-2010.pdf').read_bytes()).hexdigest() == source['pdf_sha256']
    details = {r['Sample ID']: (line, r) for line, r in enumerate(csv.DictReader((DATA / 'sample_detail_EC.csv').open()), 2)}
    result = []
    for line, row in enumerate(csv.DictReader((DATA / 'data_EC.csv').open()), 2):
        if row['rid'] != '42969':
            continue
        detail_line, detail = details[row['id']]
        group = row['id'].rsplit('-', 1)[1]
        label, marker, process_key, thickness_mm = GROUPS[group]
        assert detail[process_key].strip()
        assert detail['[elecon] remarks'] == 'Taken from the Fig.12'
        wt = float(detail['Additives'].split(';')[2])
        conductivity = float(detail['elecon'])
        log_target = float(row['log10(EC)'])
        assert math.isclose(log_target, math.log10(conductivity), abs_tol=1e-10)
        assert math.isclose(float(detail['thickness']) * 1000, thickness_mm, abs_tol=1e-10)
        assert math.isclose(float(row['log10(thickness)']), math.log10(float(detail['thickness'])), abs_tol=1e-10)
        assert math.isclose(float(row['vol%']) / wt, 4 / 7, abs_tol=1e-10)
        result.append({
            'id': row['id'], 'processed_csv_line': line, 'detail_csv_line': detail_line,
            'group': group, 'figure_legend': label, 'figure_marker': marker,
            'detail_process': detail[process_key], 'detail_shape': detail['[proc] Shape of Test Piece'],
            'wt_percent_from_detail': wt, 'vol_percent_processed': float(row['vol%']),
            'detail_conductivity_number': conductivity, 'processed_log10_ec': log_target,
            'detail_thickness_mm': thickness_mm,
            'thickness_status': 'mold_gap_not_confirmed_final_thickness' if group == '2' else 'nominal_geometry_matches_preparation_section',
            'processed_method_flags': {k: row[k] for k in ['dc', 'ac', 'two-probe']},
            'mapping_status': 'process_legend_and_loading_matched; exact_digitization_not_verified',
        })
    result.sort(key=lambda r: (int(r['group']), r['wt_percent_from_detail']))
    assert len(result) == len({r['id'] for r in result}) == 25
    assert Counter(r['group'] for r in result) == {k: 5 for k in GROUPS}
    for group in GROUPS:
        assert {r['wt_percent_from_detail'] for r in result if r['group'] == group} == {1, 3, 5, 10, 15}
    assert all(set(r['processed_method_flags'].values()) == {'0'} for r in result)
    payload = {
        'rid': '42969', 'source': source['url'], 'pdf_sha256': source['pdf_sha256'],
        'source_sha256': previous['source_sha256'],
        'inspected_pages': 'printed 923-924 (§2.2, §2.6) and 932 (Fig.12); rendered pages visually inspected',
        'figure_axes': {'x': 'MWCNT wt%', 'y': 'electrical conductivity S/cm, logarithmic'},
        'rows': result, 'row_count': 25, 'process_groups': 5,
        'read_scope': 'legend, units, nominal geometry and qualitative plotted-value agreement; no exact redigitization or uncertainty estimate',
        'issues': [
            'The processed log target equals log10 of the detail number in all 25 rows; no factor 100 occurs between these two files. Confirm dataset-wide unit convention before calling this an error or converting S/cm to S/m.',
            'All 25 vol% / detail wt% ratios equal 4/7. This observed relation does not establish a valid density conversion or its provenance.',
            'Five microinjection-compression rows use 1.2 mm as thickness. Section 2.2 describes 1.2 mm as mold-plate gap before closing; final specimen thickness is not established by that sentence.',
            'All 25 dc/ac/two-probe flags are zero despite the source method discussion; zero cannot establish absence of DC or two-probe use. Per-row apparatus and electrode geometry remain unverified.',
            'Fig.12 contains additional loadings beyond the five represented in these rows. The 25-row subset is not a complete extraction of the figure.',
            'Process groups also differ in shape and thickness. A process-effect association is not isolated causal evidence for nanotube orientation.',
            'Processed 23°C remains unsupported by the inspected electrical-method section.',
        ],
        'source_data_modified': False, 'native_issues_resolved': False, 'm1_complete': False,
    }
    save(BASE / 'abbasi-figure-audit.json', payload)
    lines = ['# Abbasi 그림12와 25행 대조', '',
        '조정자가 원문 그림과 상세표를 대조했다. 25행의 공정·충전율 연결은 확인했지만 수치 재추출과 측정 사건 검증을 완료한 것은 아니다.', '',
        '[NRC 공개 원문](' + source['url'] + ')의 인쇄 쪽 923–924(시편 준비·측정법), 932(그림12)를 확인했다. 그림은 가로축 wt%, 세로축 S/cm 로그축이다.', '',
        '## 공정별 연결', '',
        '| ID 끝자리 | 그림 범례 | 기호 | 상세표 두께(mm) | 행 수 |',
        '| --- | --- | --- | ---: | ---: |']
    for group, (label, marker, _, thickness) in GROUPS.items():
        lines.append(f'| {group} | {label} | {marker} | {thickness} | 5 |')
    lines += ['', '각 공정에 1·3·5·10·15 wt%가 있다. 추가 충전율도 그림에 표시되므로 이 25행을 그림 전체로 간주하지 않는다. 기호·곡선 위치를 시각적으로 대조했으며 픽셀 기반 수치 재추출 오차는 산정하지 않았다.', '',
        '## 새로 드러난 확인점', '',
        '- **두께:** 사출-압축 5행의 1.2 mm는 본문에서 닫히기 전 금형 간격으로 설명된다. 최종 시편 두께로 확정하지 않는다. 다른 공정의 상세표 두께는 준비 절의 명목 형상과 대응하며, 실제 전기 측정 두께를 독립 검증한 것은 아니다.',
        '- **전도도 단위:** 가공 목표값은 25행 모두 상세표 전도도 수치의 log10과 같다. 두 파일 사이에는 ×100 환산이 없다. 원문은 S/cm이므로 통합 데이터의 기준 단위를 확인해야 한다. 현 단계에서 단위 오류를 확정하거나 값을 변환하지 않는다.',
        '- **충전율:** 가공 vol% / 상세 wt%가 모두 4/7이다. 관측된 수치 관계이며 올바른 밀도 환산식의 증거는 아니다.',
        '- **방법 부호:** 25행 모두 dc·ac·two-probe가 0이다. 원문 측정법과 각 행의 장비 대응을 확인해야 하며 0을 측정법 부재로 해석하지 않는다.',
        '- **온도·해석:** 23°C는 계속 미확인이다. 공정·형상·두께가 함께 달라 공정 효과를 배향만의 인과 효과로 해석할 수 없다.', '',
        '## 행별 추적표', '',
        '전도도 열은 상세표에 저장된 수치다. 원문 S/cm 축과의 대응 후보이며 정밀 재추출을 완료한 값으로 표시하지 않는다. CSV 줄 번호는 헤더를 1로 센다.', '',
        '| 시료 ID | 가공 CSV 줄 | 상세 CSV 줄 | wt% | 가공 vol% | 상세 전도도 수치 | 가공 log10(EC) |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in result:
        lines.append(f"| {r['id']} | {r['processed_csv_line']} | {r['detail_csv_line']} | {r['wt_percent_from_detail']:g} | {r['vol_percent_processed']:.6g} | {r['detail_conductivity_number']:g} | {r['processed_log10_ec']:.6g} |")
    lines += ['', '## 이어서 할 일', '',
        '데이터 제공자의 단위·충전율 전처리 코드를 먼저 확인하고, 사출-압축 두께의 출처를 추적한다. 확인되지 않은 수치를 보정하거나 학습에 사용하지 않는다. 이 결과를 후속 교차 검토의 근거로 제공하되, 이번 조정자 확인을 에이전트 합의로 기록하지 않는다.', '',
        '원본 CSV와 PDF 해시를 재확인했다. 기존 누적 54개 협의 제출·22개 열린 쟁점과 M1 미완료 상태를 유지한다.', '']
    (DOC / 'abbasi-figure-review.md').write_text('\n'.join(lines))
    selection = json.loads((BASE / 'selection-resumed-draft.json').read_text())
    selection['summary'] = '그림12 대조: Abbasi2010의 25행을 5공정 × 5충전율로 연결했다. 단위 기준·충전율 환산·측정법 부호와 사출-압축 5행의 두께를 추가 확인해야 한다. 특히 원문 1.2 mm는 닫히기 전 금형 간격으로 설명된다. 수치 정밀 재추출·데이터 보정은 하지 않았다. 조정자 확인이며 기존 협의54개 제출·열린 쟁점22개를 유지한다.'
    selection['unresolved'] = [x for x in selection['unresolved'] if not x.startswith('Abbasi2010:')]
    selection['unresolved'] += [
        'Abbasi 그림12: 25행의 공정·충전율 연결 완료. 원문은 S/cm이며 상세→가공 전도도 수치는 그대로 로그화됐다. 통합 기준 단위와 vol%/wt%=4/7 환산 근거는 미확인이다.',
        'Abbasi 두께: 사출-압축 5행에 기록된 1.2 mm는 원문에서 금형이 닫히기 전 간격이다. 최종 전기 측정 시편 두께로 확정할 수 없다. 온도23°C와 행별 장비·전극 배치도 미확인이다.',
        'Abbasi 해석: 공정·형상·두께가 함께 달라진다. 그림의 공정별 차이를 배향 단독의 인과 효과로 판단하지 않는다. 원본값은 보존한다.',
    ]
    save(BASE / 'selection-abbasi-figure-draft.json', selection)
    save(BASE / 'discovery-runs/restart-02/selection.json', selection)
    print(json.dumps({'rows': len(result), 'groups': 5, 'thickness_gap_review_rows': 5, 'source_hashes_verified': True}))

if __name__ == '__main__':
    main()
