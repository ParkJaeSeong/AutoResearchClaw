"""Public request progress, separate from the subsequent scientific review."""
import json

from researchclaw.core.research_graph import commands, store


class RequestEpisode:
    def __init__(self, session, key, identity):
        self.session = session
        self.prefix = 'atlas-request-' + store._hash(key.encode())
        self.id = identity

    @classmethod
    def start(cls, session, key, context, previous):
        # The command key stays fixed even before the transport journal exists.
        # A changed question or predecessor must conflict, not create another run.
        intent = dict(question_ref=context['question_ref'], question=context['question'], previous=previous)
        identity = 'atlas-request-' + store._hash(key.encode()) + '-' + store._hash(store._canonical(intent))
        episode = cls(session, key, identity)
        episode.apply('start', 'episode.start', dict(
            id=identity, stage='자료 확인', title='Atlas에 연구 질문 확인 요청',
            purpose=context['question']['question'], depends_on=[], return_to=None,
            return_reason=None, review_required=False))
        episode.note('send', 'tool',
                     '연구 질문에 필요한 근거를 Atlas 보유 자료에서 확인하도록 요청합니다. '
                     '답변 수신 뒤 연구에 적용할 범위를 별도로 검토합니다.')
        return episode

    @classmethod
    def existing(cls, session, key):
        prefix = 'atlas-request-' + store._hash(key.encode()) + '-'
        rows = store.read_head(session.root)['state'].get('work_episodes', {})
        identity = next((identity for identity in rows if identity.startswith(prefix)), None)
        return cls(session, key, identity) if identity else None

    def apply(self, name, operation, payload):
        return commands.apply_command(self.session.root, operation=operation, payload=payload,
            expected_head=store.read_head(self.session.root)['id'],
            command_id=self.prefix + ':' + name)

    def closed(self):
        return store.read_head(self.session.root)['state']['work_episodes'][self.id]['conclusion'] is not None

    def note(self, name, kind, text):
        if not self.closed():
            self.apply(name, 'episode.note', dict(id=self.id, kind=kind, author='조정자', text=text))

    def accepted(self, row):
        self.note('accepted', 'tool', 'Atlas가 확인 요청을 접수했습니다. 답변 수신과 연구 판단은 아직 별도입니다.\n'
                  + json.dumps(dict(job_id=row['job']['id']), ensure_ascii=False, sort_keys=True))

    def error(self):
        # Reporting must never replace the original failure, including disk errors.
        try:
            self.note('retryable-error', 'tool',
                      '요청 처리 상태를 확인하지 못했습니다. 같은 요청으로 다시 확인할 수 있습니다. '
                      '현재 기록만으로 전송 실패나 연구 결과를 확정하지 않습니다.')
        except Exception:
            pass

    def observe(self, result):
        if self.closed():
            return
        stage = result['stage']
        if stage == 'review_input_ready':
            packet = result['packet']
            diagnostic = packet['atlas_status'] != 'completed'
            self.note('input', 'output',
                      '수신 자료를 후속 검토 입력으로 고정했습니다.\n' + json.dumps(dict(
                          packet_sha256=result['packet_sha256'], evidence_ref=packet['evidence_ref'],
                          qa_ref=packet['qa_ref'], job_id=packet['execution']['job_id'],
                          atlas_status=packet['atlas_status']), ensure_ascii=False, sort_keys=True))
            self.apply('conclude', 'episode.conclude', dict(id=self.id, execution_status='finished',
                judgment='진단·제한 검토용 자료를 수신했습니다.' if diagnostic else 'Atlas 답변을 수신하고 검토 입력을 고정했습니다.',
                remaining='수신은 과학적 승인이나 원문 직접 검증 완료를 뜻하지 않습니다.',
                next_action='받은 근거의 적용 범위와 미확인 사항을 후속 검토합니다.',
                next_reason='자료 확보와 과학적 판단을 구분하기 위해서입니다.'))
        else:
            attention = stage == 'needs_attention'
            reason = result.get('reason')
            text = ('답변 자료가 없어 실행 상태를 확인해야 합니다. 같은 요청으로 다시 확인할 수 있습니다.'
                    if reason == 'terminal_qa_missing' else
                    'Atlas 실행 상태를 점검해야 합니다. 같은 요청으로 다시 확인할 수 있습니다.'
                    if attention else 'Atlas가 자료를 확인하고 있습니다. 같은 요청에서 답변을 기다립니다.')
            observation = dict(stage=stage, atlas_status=result['atlas_status'], reason=reason)
            self.note('observation-' + store._hash(store._canonical(observation)), 'tool', text)
