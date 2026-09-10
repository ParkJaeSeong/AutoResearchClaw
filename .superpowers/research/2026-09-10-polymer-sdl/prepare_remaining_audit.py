"""Resume independent PC/CNT source triage while rid44100 access is pending."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

BASE=Path(__file__).resolve().parent
DATA=BASE/'discovery-runs/restart-02/coordinator-audit'
DOC=BASE.parents[2]/'docs/research/2026-09-10-polymer-sdl/remaining-source-audit.md'

def main():
    rows=list(csv.DictReader((DATA/'data_EC.csv').open()))
    raw={r['Sample ID']:r for r in csv.DictReader((DATA/'sample_detail_EC.csv').open())}
    previous=json.loads((BASE/'target-pair-audit.json').read_text())
    for name,digest in previous['source_sha256'].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest
    selected=[r for r in rows if r['PID']=='P150011' and r['filler']=='CNT' and r['rid']!='44100']
    groups=defaultdict(list)
    for r in selected:groups[r['rid']].append(r)
    assert len(selected)==123 and len(groups)==15 and len({r['id'] for r in selected})==123
    result=[]
    for rid,rr in groups.items():
        temperature=sum(not raw[r['id']]['[elecon] temp'].strip() for r in rr)
        thickness=sum(not raw[r['id']]['log10(thickness)'].strip() for r in rr)
        # Disclosed missing-condition counts are review priority signals, not a quality score.
        actions=[]
        if temperature:actions.append('온도 원기록·가공값 생성 경로 확인')
        if thickness:actions.append('두께 원기록·가공 상수 근거 확인')
        if any(float(r['temperature'])!=23 for r in rr):actions.append('23 외 온도의 의미·단위·측정/공정 구분 확인')
        actions+=['측정법 부호·주파수·단위·원문 추출 위치 대조','문헌·저자 그룹과 실제 측정 계보 구분']
        result.append(dict(rid=rid,rows=len(rr),sample_ids=[r['id'] for r in rr],
          references=sorted({raw[r['id']]['Reference'] for r in rr}),
          missing_detail_temperature_rows=temperature,missing_detail_log_thickness_rows=thickness,
          processed_temperatures=sorted({r['temperature'] for r in rr}),
          actions=actions,status='queued_source_verification_not_complete'))
    result.sort(key=lambda x:(-(x['missing_detail_temperature_rows']+x['missing_detail_log_thickness_rows']),-x['rows'],x['rid']))
    payload={'status':'resumed_independent_source_triage','pending_external':'rid44100 full Fig.4 remains behind publisher CAPTCHA; no new full-text evidence',
             'held_rows':14,'remaining_rows':123,'remaining_sources':15,'sources':result,
             'source_data_modified':False,'native_issues_resolved':False,'model_training_executed':False}
    (BASE/'remaining-source-audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    text=['# 남은 PC/CNT 문헌 감사 우선표','',
      'rid44100 원문 접근을 기다리는 동안 진행한 독립 작업이다. 보류14행을 제외한다고 가정한123행·123시료·15문헌을 대상으로 상세표 연결과 조건 공백을 정리했다. 실제 자료 필터·삭제·학습은 수행하지 않았다.',
      '', '우선순위는 상세 온도·로그 두께가 비어 있는 행의 합, 다음으로 문헌의 행 수를 기준으로 정했다. 같은 행이 두 항목에 중복될 수 있으며 품질 점수나 독립 표본 수가 아니다. 빈칸이 적다고 검증된 자료로 간주하지 않는다.',
      '', '| 문헌 ID | 행 | 상세 온도 빈칸 | 상세 로그 두께 빈칸 | 가공 온도값 |', '| --- | ---: | ---: | ---: | --- |']
    for r in result:text.append(f"| {r['rid']} | {r['rows']} | {r['missing_detail_temperature_rows']} | {r['missing_detail_log_thickness_rows']} | {', '.join(r['processed_temperatures'])} |")
    text+=['','## 출처별 다음 확인','']
    for r in result:
        text += [f"### rid{r['rid']}",'',*r['references'],'','; '.join(r['actions'])+'.','']
    text += ['## 재개 지점','',
      '현재 파일 연결·조건 공백 집계까지 완료했다. 위 문헌 전문을 새로 읽거나 쟁점을 해결한 상태는 아니다. 원문 확보 시 각 rid별 측정 사건–시료–가공행 대응표를 채운다.',
      'rid44100은 그림4의 축·범례·캡션 및 측정 본문이 필요하다. 그동안 표의 높은 우선순위 문헌부터 출처와 조건을 확인할 수 있다. 기존54개 협의 제출과22개 열린 쟁점은 유지한다.']
    DOC.write_text('\n'.join(text)+'\n')
    print(json.dumps({'sources':15,'rows':123,'first_priorities':[{k:r[k] for k in ['rid','rows','missing_detail_temperature_rows','missing_detail_log_thickness_rows']} for r in result[:3]]}))

if __name__=='__main__':main()
