"""Expose audited council outcomes without resolving scientific issues."""
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save
BASE=Path(__file__).resolve().parent
RUN=BASE/'selection-hypotheses-03'

def main():
    audit=json.loads((RUN/'audit.json').read_text())
    assert audit['answer_match'] and audit['phase_disclosure_checked'] and audit['new_submissions']==9
    status=json.loads((RUN/'status.json').read_text())
    s=json.loads((BASE/'selection-abbasi-figure-draft.json').read_text())
    n=audit['total_submissions'];issues=audit['open_issues']
    s['summary']=f'공개 코드 추적과 질문4차 교차 검토 완료: 저자 저장소의 코드는 공저자 연결과 최대 그룹 분할로 expt를 만든다. 단위·온도·두께·충전율 전처리 코드는 확인한 커밋에 없어 생성 근거는 미해결이다. 세 역할의 독립 의견→공개 반박→최종 의견9개를 원응답과 대조했다(누적{n}개, 열린 쟁점{issues}개). 구체적 의견은 02 연구 질문 → 4차 개정 → 공개 대화에서 확인할 수 있다. M1 완료나 학습·실험 착수 승인이 아니다.'
    s['unresolved'] += [
      '공개 코드 후속: expt를 독립 실험실·배치로 간주하지 않는다. 분할 전 공저자 연결성분과 최종 rid–expt 대응, 이름 매칭·누락·중복을 확인한다. 최대 그룹 나머지 누락은 조건부 우려이며 실제 EC 행 손실로 확정하지 않는다.',
      '전처리 출처: 확인한 저자 저장소 커밋93d74c135d63183a22a6eb88eb31be24892d7959에는 단위·온도·두께·충전율 생성 코드가 없다. 저장소 전체 역사나 다른 보충자료에 전혀 없다는 뜻은 아니다.',
    ]
    save(BASE/'selection-preprocessing-draft.json',s)
    save(BASE/'discovery-runs/restart-02/selection.json',s)
    doc=BASE.parents[2]/'docs/research/2026-09-10-polymer-sdl/preprocessing-review.md'
    text=doc.read_text().split('\n## 실제 협의 결과')[0]
    text+='\n## 실제 협의 결과\n\n'
    text+=f'신규 제출 9개를 원응답과 대조했다. 누적 {n}개 제출, 열린 쟁점 {issues}개다. 각 초기 입력에 동료 의견이 없고 반박·최종 입력에는 앞 단계 공개 의견만 포함된 것을 확인했다. 모델 다양성이나 강제 접근 격리를 입증한 것은 아니다.\n\n'
    for f in sorted(RUN.glob('*-final-*/answer.json')):
        role=f.parent.name.rsplit('-',1)[1];answer=json.loads(f.read_text())
        text+=f'### {role}: {answer["recommendation"]}\n\n{answer["rationale"]}\n\n'
    text+='진행 정책: '+json.dumps({'ready':status['ready'],'reason_codes':status['reason_codes']},ensure_ascii=False)+'\n'
    doc.write_text(text)
    p=doc.parent/'README.md';t=p.read_text();anchor='[최신 그림12·25행 대조]'
    if '[최신 공개 코드·교차 검토]' not in t:t=t.replace(anchor,'[최신 공개 코드·교차 검토](preprocessing-review.md): 질문4차 협의와 전처리 출처 확인 결과.\n'+anchor,1)
    p.write_text(t)
    print(json.dumps({'published':True,'submissions':n,'open_issues':issues,'ready':status['ready']},ensure_ascii=False))

if __name__=='__main__': main()
