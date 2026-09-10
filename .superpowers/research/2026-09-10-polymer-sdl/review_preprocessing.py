"""Freeze upstream-code reading and submit it to a new native questions council."""
import hashlib
import json
import review_selection_hypotheses as engine
import study_host as host
from researchclaw.core.research_graph.m1_nodes import review_node

BASE = host.BASE
RUN = BASE / 'selection-hypotheses-03'
DATA = BASE / 'discovery-runs/restart-02/coordinator-audit'

def main():
    RUN.mkdir(exist_ok=False)
    tree = json.loads((DATA/'upstream-tree.json').read_text())
    notebook = json.loads((DATA/'upstream-make_expt_id.ipynb').read_text())
    cells = [{'cell': i, 'source': ''.join(c['source'])} for i,c in enumerate(notebook['cells']) if c['cell_type']=='code']
    audit = {'repository': 'https://github.com/shimakawa-hvg/expt-group-partitioning',
      'commit': tree['commit'], 'paths': [x['path'] for x in tree['tree']['tree']],
      'sha256': {name: hashlib.sha256((DATA/name).read_bytes()).hexdigest() for name in ['upstream-README.md','upstream-make_expt_id.ipynb']},
      'code_cells': cells, 'reading_scope': 'All five code cells and README at pinned current commit; notebook not executed.',
      'findings': ['公開されているノートブックはexptグループ生成用であり、単位・温度・厚さ・充填率の前処理コードはこのコミットのファイル一覧にない。',
        'Code merges coauthor connections, then partitions the largest rid group to mitigate imbalance. expt is not an independently verified lab or batch identifier.',
        'The largest-group partition uses floor division and fixed-size slices; a remainder could be omitted if nonzero. This is a conditional code concern, not a demonstrated loss in the provided EC CSV.',
        'Author matching truncates names and uses str.contains with default regex semantics. Collisions or overmatching are possible; actual affected records are unverified.',
        'README and notebook describe later polymer/filler restriction but do not specify complete selection or preprocessing rules.'],
      'unit_conversion_resolved': False, 'thickness_resolved': False, 'temperature_resolved': False,
      'source_data_modified': False}
    audit['findings'][0]='공개 노트북은 expt 그룹 생성용이다. 이 커밋의 파일 목록에 단위·온도·두께·충전율 전처리 코드는 없다.'
    host.save(BASE/'preprocessing-code-audit.json', audit)
    figure=json.loads((BASE/'abbasi-figure-audit.json').read_text())
    for name,digest in figure['source_sha256'].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest
    report='''# 공개 전처리 코드 확인과 후속 교차 검토

저자 저장소의 현재 커밋을 고정하여 README와 노트북의 코드 셀 5개를 모두 읽었다. 코드는 실행하지 않았다.

[확인한 저장소](https://github.com/shimakawa-hvg/expt-group-partitioning/tree/COMMIT)

- 제공 코드는 저자 연결 관계로 expt를 만들고 큰 그룹을 분할한다. 실험실·배치를 직접 식별하는 코드가 아니다.
- 이 커밋에는 단위·온도·두께·충전율의 전처리 코드가 없다. 이전에 관측한 23°C, 1.2 mm, vol%/wt%=4/7의 생성 근거는 해결되지 않았다.
- 최대 그룹을 정수 몫만큼 자르는 구현은 나머지가 있을 때 누락 가능성이 있다. 실제 EC 행의 누락을 입증한 것은 아니다.
- 이름 축약 및 정규식 문자열 검색은 잘못된 연결 가능성이 있어 확인이 필요하다. 실제 영향받은 문헌은 아직 특정하지 않았다.

[그림12 대조](abbasi-figure-review.md)의 25행·5공정 연결과 함께 검토한다. 공정·형상·두께가 함께 달라지므로 배향 단독의 인과 효과로 해석하지 않는다. 데이터 전체 기준 단위도 먼저 확인해야 한다.

## 교차 검토 질문

1. H1을 새 문헌 예측으로 제한하더라도 현재 expt 분할을 사용할 수 있는가? 추가 확인이나 민감도 분석이 필요한가?
2. 두께·단위·조건이 불명확한 자료에서 H2의 기전 판별을 주장할 수 있는가?
3. H3의 실행 전 검사에서 불확실한 출처를 어떤 조건으로 보류·추가 확인해야 하는가?

독립 초기 의견 → 공개 반박 → 최종 의견을 실제 연구 기록에 등록한다. 합의만으로 자료 검증·쟁점 해소·M1 완료를 선언하지 않는다.
'''.replace('COMMIT',tree['commit'])
    (host.REPO/'docs/research/2026-09-10-polymer-sdl/preprocessing-review.md').write_text(report)
    previous=json.loads((BASE/'selection-abbasi-figure-draft.json').read_text())
    content={'questions':[{'question':h['statement'],'rationale':h['test']+' 기존 한계: '+h['limits']} for h in previous['hypotheses']],
      'agent_assumptions':[report,
        '최신 원문 대조 결과(조정자 읽기; 검토자 직접 독해 아님): '+json.dumps({k:v for k,v in figure.items() if k!='rows'},ensure_ascii=False),
        '공개 코드의 전체 셀과 확인 범위: '+json.dumps(audit,ensure_ascii=False),
        '핵심 검토: 단위 환산 코드를 확보하지 못한 상황에서 과거 관측을 오류로 단정하지 말 것. expt의 공저자 연결·최대 그룹 분할이 평가 독립성에 주는 영향을 논의할 것. 코드의 조건부 누락 가능성을 실제 데이터 손실로 주장하지 말 것.',
        '이전 22개 쟁점은 열려 있다. 기존 쟁점에 포함되는 내용은 중복 제안하지 말고 rationale에 연결하라. 원문 수집·질문 구체화는 진행할 수 있으나 현재 데이터 학습·물리 실험·corpus 승인은 보류한다.']}
    host.save(RUN/'input.json',content)
    artifact=host.register('questions',content,('scope',),reason='Abbasi 그림12 및 공개 expt 생성 코드 확인을 반영해 자료 적합성과 평가 분할을 교차 검토한다.')
    host.save(RUN/'artifact.json',artifact)
    engine.RUN=RUN
    host.host_review=engine.host_review
    issues=host.council(artifact)
    status=review_node(host.snap(),'questions');host.save(RUN/'status.json',status)
    print(json.dumps({'ready':status['ready'],'reason_codes':status['reason_codes'],'new_issues':len(issues)},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
