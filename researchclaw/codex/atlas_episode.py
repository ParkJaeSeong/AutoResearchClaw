"""Public episode recording for the existing Atlas council executor.

The council owns barriers and resumability; this adapter only records already
accepted public reports through its durable apply function.
"""
import json
from researchclaw.core.research_graph import store

_ROLES = {'domain':'분야 검토자', 'methodology':'평가 방법 검토자', 'critical':'실행 조건 검토자'}
_PHASES = {'initial':'독립 검토', 'response':'상호 검토', 'final':'최종 의견'}
_RECOMMENDATIONS = {'ready':'사용 가능 의견', 'ready_with_limits':'제한된 사용 의견',
                    'revise':'수정 필요 의견', 'defer':'판단 보류 의견'}


class CouncilEpisode:
    def __init__(self, key, apply):
        self.id = 'atlas-council-' + store._hash(key.encode())
        self.apply = apply

    def start(self, shared):
        self.apply('episode-start', 'episode.start', lambda: dict(
            id=self.id, stage='근거 검토', title='Atlas 근거의 연구 적용 범위 검토',
            purpose='같은 Atlas 답변을 분야·평가 방법·실행 조건 관점에서 검토하고 남은 이견을 정리합니다.',
            depends_on=[], return_to=None, return_reason=None, review_required=True))
        self.note('input', 'tool', '조정자',
                  '이미 받은 Atlas 답변을 공통 검토 입력으로 사용합니다. 새 조회 호출이 아닙니다.\n'
                  + json.dumps(dict(packet_sha256=shared['packet_sha256'],
                                    evidence_ref=shared['packet']['evidence_ref']), ensure_ascii=False))

    def note(self, key, kind, author, text):
        self.apply('episode-'+key, 'episode.note', lambda: dict(
            id=self.id, kind=kind, author=author, text=text))

    def phase(self, phase, roles, results):
        # Caller must first commit every native submission for this phase.
        for role, result in zip(roles, results):
            self.note(phase+'-'+role, 'dialogue', f'{_PHASES[phase]} · {_ROLES[role]}',
                      result['answer']['rationale'])

    def finish(self, result):
        recommendations = [r['recommendation'] for r in result['finals']]
        judgment = ' / '.join(f'{_RECOMMENDATIONS[key]} {recommendations.count(key)}명'
                              for key in _RECOMMENDATIONS if key in recommendations)
        self.note('output', 'output', '조정자',
                  '원래 검토 의견과 근거를 연결하는 기록입니다.\n'
                  + json.dumps({key: result[key] for key in ('council_id','review_ref','submission_refs','packet_sha256')}, ensure_ascii=False))
        self.apply('episode-conclude', 'episode.conclude', lambda: dict(
            id=self.id, execution_status='finished', judgment=judgment,
            remaining='각 검토자의 최종 의견에 남은 조건과 이견을 확인해야 합니다.',
            next_action='개발 검토 후 다음 연구 작업을 정합니다.',
            next_reason='검토 의견의 합의 여부와 실제 근거의 충분성을 구분해 판단하기 위해서입니다.'))
