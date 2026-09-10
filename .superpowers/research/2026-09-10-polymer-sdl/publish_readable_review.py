"""Add a clearly labeled reading guide; preserve all original council statements."""
import json
from pathlib import Path
from researchclaw.codex.literature_loop import save
BASE=Path(__file__).resolve().parent
run=BASE/'selection-hypotheses-03'
audit=json.loads((run/'audit.json').read_text())
assert audit['answer_match'] and audit['new_submissions']==9
originals={p.parent.name.rsplit('-',1)[1]:json.loads(p.read_text()) for p in run.glob('*-final-*/answer.json')}
assert set(originals)=={'domain','methodology','critical'}
s=json.loads((BASE/'selection-preprocessing-draft.json').read_text())
s['summary']='지금은 자료를 점검하면서 연구 질문을 다듬고 있습니다. 데이터의 단위·두께·온도와 같은 연구팀 자료의 중복 여부를 더 확인해야 합니다. 에이전트들은 질문을 구체화하는 작업은 계속하되, 이 자료로 모델을 학습하거나 실제 실험을 시작하는 것은 보류하자는 의견입니다.'
s['reading_guide']=[
 '소재 전문가: 공정을 바꿨을 때 전도도가 달라지지만 시편 모양과 두께도 함께 달라집니다. 지금 자료만으로 “나노튜브의 방향 때문에 달라졌다”고 결론낼 수 없습니다. 같은 시편의 구조와 전도도를 연결해서 확인해야 합니다.',
 '평가 방법 검토자: 같은 연구팀이나 같은 원자료에서 나온 데이터가 학습용과 평가용에 나뉘어 들어가면 성능이 좋아 보일 수 있습니다. 저자 연결과 자료 재사용을 확인해야 합니다. 저자별로 묶는 것만으로 독립적인 자료임이 보장되지는 않습니다.',
 '실험·실행 검토자: 결과를 못 얻은 실험이나 사람이 수정해 준 작업도 비용과 성과에 포함해야 합니다. 출처를 모르는 조건은 “잘못됐다”고 확정하지 말고 추가 확인 대상으로 남겨야 합니다.',
 '대화에서 보완한 점: 소재를 직접 관찰하거나 별도의 판정자를 둔다고 해서 원인을 바로 확정할 수는 없습니다. 서로 다른 원인이라면 어떤 결과 차이가 나와야 하는지 먼저 정해야 한다는 의견을 반영했습니다.',
 '다음 할 일: 논문과 연구팀의 연결을 데이터 분류와 대조하고, 단위·두께·온도가 어디서 나온 값인지 추적합니다. 아직 어느 가설이 맞는지 확인한 단계는 아닙니다.'
]
save(BASE/'selection-readable-draft.json',s)
save(BASE/'discovery-runs/restart-02/selection.json',s)
print('Published a reading guide derived from three saved final statements; original council unchanged.')
